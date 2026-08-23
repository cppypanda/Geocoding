"""Payment provider adapters used by the recharge workflow.

The YunGouOS implementation mirrors the payment flow used by URPA:
server-created orders, MD5-signed provider requests, signed callbacks, and
active order queries as a fallback when callbacks are delayed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

import requests


YUNGOU_ALIPAY_NATIVE_URL = "https://api.pay.yungouos.com/api/pay/alipay/nativePay"
YUNGOU_ORDER_QUERY_URL = "https://api.pay.yungouos.com/api/system/order/getPayOrderInfo"


class PaymentProviderError(RuntimeError):
    """Raised when a payment provider request or response is invalid."""


@dataclass(frozen=True)
class YungouConfig:
    mch_id: str
    pay_key: str
    notify_url: str
    app_id: str = ""


@dataclass(frozen=True)
class PaymentConfirmation:
    order_number: str
    amount_cny: float
    paid: bool
    provider_trade_no: str | None = None
    buyer_logon_id: str | None = None
    paid_at: str | None = None
    notify_payload: str | None = None


def _config_value(config: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(config.get(name) or "").strip()
        if value:
            return value
    return ""


def get_yungou_config(config: Mapping[str, Any], default_notify_url: str = "") -> YungouConfig | None:
    mch_id = _config_value(config, "YUNGOUOS_MCH_ID", "YUNGOU_MCH_ID")
    pay_key = _config_value(config, "YUNGOUOS_PAY_KEY", "YUNGOU_PAY_KEY")
    notify_url = _config_value(config, "YUNGOUOS_NOTIFY_URL", "YUNGOU_NOTIFY_URL") or default_notify_url
    if not mch_id or not pay_key or not notify_url:
        return None
    return YungouConfig(
        mch_id=mch_id,
        pay_key=pay_key,
        notify_url=notify_url,
        app_id=_config_value(config, "YUNGOUOS_APP_ID", "YUNGOU_APP_ID"),
    )


def yungou_sign(params: Mapping[str, Any], pay_key: str) -> str:
    """Return the uppercase MD5 signature used by YunGouOS."""
    signing_text = "&".join(f"{key}={params[key]}" for key in sorted(params))
    signing_text = f"{signing_text}&key={pay_key}"
    return hashlib.md5(signing_text.encode("utf-8")).hexdigest().upper()


def _provider_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise PaymentProviderError("支付服务返回了无效数据") from exc
    if not response.ok:
        raise PaymentProviderError(f"支付服务请求失败（HTTP {response.status_code}）")
    if not isinstance(payload, dict) or int(payload.get("code", -1)) != 0:
        message = payload.get("msg") or payload.get("message") if isinstance(payload, dict) else None
        raise PaymentProviderError(str(message or "支付服务未接受请求"))
    return payload


def create_yungou_alipay_payment(
    *,
    order_number: str,
    amount_cny: float,
    subject: str,
    points: int,
    config: YungouConfig,
    timeout: float = 12,
) -> str:
    signed_params = {
        "body": subject,
        "mch_id": config.mch_id,
        "out_trade_no": order_number,
        "total_fee": f"{amount_cny:.2f}",
    }
    params: dict[str, str] = {
        **signed_params,
        "sign": yungou_sign(signed_params, config.pay_key),
        "type": "2",
        "attach": json.dumps({"points": points}, ensure_ascii=False, separators=(",", ":")),
        "notify_url": config.notify_url,
    }
    if config.app_id:
        params["app_id"] = config.app_id

    response = requests.post(YUNGOU_ALIPAY_NATIVE_URL, data=params, timeout=timeout)
    payload = _provider_json(response)
    payment_url = payload.get("data")
    if not isinstance(payment_url, str) or not payment_url.strip():
        raise PaymentProviderError("支付服务未返回支付宝支付链接")
    return payment_url.strip()


def query_yungou_order(
    order_number: str,
    config: YungouConfig,
    *,
    timeout: float = 10,
) -> PaymentConfirmation | None:
    signed_params = {"mch_id": config.mch_id, "out_trade_no": order_number}
    params = {**signed_params, "sign": yungou_sign(signed_params, config.pay_key)}
    response = requests.get(YUNGOU_ORDER_QUERY_URL, params=params, timeout=timeout)
    payload = _provider_json(response)
    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    status = str(
        data.get("status")
        or data.get("orderStatus")
        or data.get("tradeStatus")
        or data.get("pay_status")
        or ""
    ).upper()
    paid = status in {"1", "2", "SUCCESS", "PAID", "PAY_SUCCESS", "TRADE_SUCCESS"} or bool(
        data.get("payNo") or data.get("pay_no")
    )
    if not paid:
        return None

    amount = float(
        data.get("money")
        or data.get("total_fee")
        or data.get("totalFee")
        or data.get("amount")
        or 0
    )
    if amount <= 0:
        raise PaymentProviderError("支付服务查单结果缺少有效金额")
    return PaymentConfirmation(
        order_number=order_number,
        amount_cny=amount,
        paid=True,
        provider_trade_no=_first_text(data, "orderNo", "payNo", "tradeNo", "transactionId"),
        buyer_logon_id=_first_text(data, "openId", "buyer", "buyerLogonId"),
        paid_at=_first_text(data, "payTime", "pay_time", "timeEnd"),
        notify_payload=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    )


def parse_yungou_notify(params: Mapping[str, Any], config: YungouConfig) -> PaymentConfirmation:
    normalized = {key: str(value or "") for key, value in params.items()}
    sign_params = {
        "code": normalized.get("code", ""),
        "mchId": normalized.get("mchId") or normalized.get("mch_id", ""),
        "money": normalized.get("money", ""),
        "orderNo": normalized.get("orderNo", ""),
        "outTradeNo": normalized.get("outTradeNo") or normalized.get("out_trade_no", ""),
        "payNo": normalized.get("payNo", ""),
    }
    if sign_params["mchId"] != config.mch_id:
        raise PaymentProviderError("支付回调商户号不匹配")
    signature = normalized.get("sign", "")
    if not signature or signature.upper() != yungou_sign(sign_params, config.pay_key):
        raise PaymentProviderError("支付回调签名验证失败")
    try:
        amount = float(sign_params["money"])
    except (TypeError, ValueError) as exc:
        raise PaymentProviderError("支付回调金额无效") from exc
    if not sign_params["outTradeNo"] or amount <= 0:
        raise PaymentProviderError("支付回调缺少订单号或金额")
    return PaymentConfirmation(
        order_number=sign_params["outTradeNo"],
        amount_cny=amount,
        paid=sign_params["code"] == "1",
        provider_trade_no=sign_params["payNo"] or sign_params["orderNo"] or None,
        buyer_logon_id=normalized.get("openId") or normalized.get("buyer") or None,
        notify_payload=json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
    )


def _first_text(data: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
