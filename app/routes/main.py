from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request, send_file, current_app
from ..services import geocoding_apis
from ..utils import address_processing
from ..models import LocationType # Import SQLAlchemy model
from .. import db # Import db instance
import json
import jionlp as jio
import asyncio
import traceback
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import simplekml
import io
import os
import zipfile
from datetime import datetime
import tempfile

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """主页，直接渲染index.html，并传入充值套餐数据"""
    packages = current_app.config.get('RECHARGE_PACKAGES', {})
    return render_template('index.html', packages=packages)

@main_bp.route('/get_location_types', methods=['GET'])
def get_location_types():
    """获取所有已批准的地名后缀类型"""
    try:
        approved_types = db.session.query(LocationType.name).filter_by(status='approved').order_by(db.func.length(LocationType.name).desc()).all()
        types = [item[0] for item in approved_types]
        return jsonify({'success': True, 'types': types})
    except Exception as e:
        # 在实际应用中，这里应该有更详细的日志记录
        print(f"获取地名类型时出错: {e}")
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500

@main_bp.route('/record_used_suffixes', methods=['POST'])
def record_used_suffixes():
    """记录一次地理编码中使用过的后缀列表。这是一个即发即忘的接口。"""
    try:
        data = request.json
        suffixes = data.get('suffixes', [])
        
        if suffixes and isinstance(suffixes, list):
            current_time = datetime.utcnow()
            for suffix_name in suffixes:
                # Find if the suffix already exists
                loc_type = LocationType.query.filter_by(name=suffix_name).first()
                if loc_type:
                    # If it exists, update usage count and last used time
                    loc_type.usage_count += 1
                    loc_type.last_used_at = current_time
                else:
                    # If it doesn't exist, create a new one
                    new_loc_type = LocationType(
                        name=suffix_name,
                        status='pending', # New suffixes are pending approval
                        source='user_generated',
                        usage_count=1,
                        created_at=current_time,
                        last_used_at=current_time
                    )
                    db.session.add(new_loc_type)
            db.session.commit()
            
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        # 由于这是个后台记录接口，即使出错也不应影响前端主流程
        print(f"记录使用过的后缀时出错: {e}")
        # 返回成功，避免给前端带来不必要的错误提示
        return jsonify({'success': True})

@main_bp.route('/user_agreement')
def user_agreement():
    return render_template('user_agreement.html')

@main_bp.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@main_bp.route('/jionlp_autocomplete', methods=['POST'])
def jionlp_autocomplete():
    """使用 jionlp 自动补全地址的行政区划。"""
    try:
        data = request.json
        addresses = data.get('addresses', [])
        
        if not addresses or not isinstance(addresses, list):
            return jsonify({'success': False, 'message': '地址列表不能为空'}), 400
        
        # 使用列表推导式和新的工具函数来处理地址列表
        completed_addresses = [address_processing.complete_address_jionlp(addr) for addr in addresses]
        
        return jsonify({
            'success': True,
            'completed_addresses': completed_addresses
        })
        
    except Exception as e:
        print(f"自动补全地址时出错: {e}")
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500

@main_bp.route('/export', methods=['POST'])
def export_data():
    """导出数据为不同格式"""
    try:
        data = request.json
        export_format = data.get('format')
        results = data.get('data', [])
        location_name = data.get('location_name', 'geocoding_results')

        if not results:
            return jsonify({'error': '没有可导出的数据'}), 400

        df = pd.DataFrame(results)

        if export_format == 'xlsx':
            # 导出为 Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='results')
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'{location_name}.xlsx'
            )

        if export_format == 'kml':
            # 导出为 KML（需提供 WGS84 坐标 lng/lat）
            if 'lng' not in df.columns or 'lat' not in df.columns:
                return jsonify({'error': '数据缺少经纬度信息，无法导出为KML'}), 400

            kml = simplekml.Kml()
            for _, row in df.iterrows():
                try:
                    lng = float(row['lng'])
                    lat = float(row['lat'])
                except Exception:
                    continue
                # KML显示名称优先使用“原始地址”，避免被显示为标准化后的详细地址
                address_original = str(row.get('address') or '')
                name_standardized = str(row.get('name') or '')  # 可能为 formatted_address
                province = str(row.get('province') or '')
                city = str(row.get('city') or '')
                district = str(row.get('district') or '')
                desc_parts = []
                if province or city or district:
                    desc_parts.append(f"{province}{city}{district}")
                api = row.get('api')
                if api:
                    desc_parts.append(f"API: {api}")
                confidence = row.get('confidence')
                if pd.notna(confidence):
                    try:
                        conf_pct = float(confidence) * 100.0
                        desc_parts.append(f"置信度: {conf_pct:.1f}%")
                    except Exception:
                        pass
                llm_reason = row.get('llm_reason')
                if pd.notna(llm_reason) and llm_reason:
                    desc_parts.append(f"说明: {llm_reason}")
                # 若存在标准化地址且不同于原始地址，则附加到描述中
                if name_standardized and name_standardized != address_original:
                    desc_parts.insert(0, f"标准化地址: {name_standardized}")
                # 无论如何，将原始地址也放入描述顶部，便于查看
                if address_original:
                    desc_parts.insert(0, f"原始地址: {address_original}")

                pnt = kml.newpoint(name=(address_original or '地点'), coords=[(lng, lat)])
                if desc_parts:
                    pnt.description = "\n".join(desc_parts)

            # simplekml 无需写临时文件，直接获取 XML 字符串
            kml_bytes = kml.kml().encode('utf-8')
            output = io.BytesIO(kml_bytes)
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.google-earth.kml+xml',
                as_attachment=True,
                download_name=f'{location_name}.kml'
            )

        if export_format == 'shp':
            if 'lng' not in df.columns or 'lat' not in df.columns:
                return jsonify({'error': '数据缺少经纬度信息，无法导出为SHP'}), 400

            # 确保列名是10个字符以内，这是Shapefile的限制
            df.columns = [col[:10] for col in df.columns]

            geometry = [Point(xy) for xy in zip(df['lng'], df['lat'])]
            gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

            # 使用临时目录写入Shapefile，再打包为Zip返回，避免内存写入兼容性问题
            with tempfile.TemporaryDirectory() as tmpdir:
                shp_path = os.path.join(tmpdir, f'{location_name}.shp')
                gdf.to_file(shp_path, driver='ESRI Shapefile', encoding='utf-8')

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    base = os.path.join(tmpdir, location_name)
                    # 组件文件列表
                    for ext in ['shp', 'shx', 'dbf', 'prj', 'cpg']:
                        fpath = f'{base}.{ext}'
                        if os.path.exists(fpath):
                            # 在Zip里使用文件名（不含路径）
                            zf.write(fpath, arcname=f'{location_name}.{ext}')

                zip_buffer.seek(0)
                return send_file(
                    zip_buffer,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f'{location_name}.zip'
                )

        # 其他不支持的格式
        else:
            return jsonify({'error': '不支持的导出格式'}), 400

    except Exception as e:
        print(f"导出数据时出错: {e}")
        traceback.print_exc()
        return jsonify({'error': f'服务器内部错误: {e}'}), 500 