def test_app_creation(app):
    """测试：应用实例是否能被成功创建"""
    assert app is not None

def test_index_page_loads(client):
    """测试：访问首页'/'是否成功 (返回 HTTP 200)"""
    response = client.get('/')
    assert response.status_code == 200