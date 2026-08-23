# URPA 同款收款配置

系统会优先使用 URPA 的 YunGouOS 支付宝扫码支付链路；未配置 YunGouOS 时，回退到支付宝开放平台网页支付。

## YunGouOS（推荐）

在生产环境配置：

```dotenv
YUNGOUOS_MCH_ID=
YUNGOUOS_PAY_KEY=
YUNGOUOS_APP_ID=
YUNGOUOS_NOTIFY_URL=https://你的域名/api/pay/yungouos/notify
PAYMENT_PUBLIC_BASE_URL=https://你的域名
```

`YUNGOUOS_APP_ID` 可按商户配置留空。生产环境必须确保回调地址可由公网通过 HTTPS 访问。

## 支付宝开放平台回退

```dotenv
ALIPAY_APP_ID=
ALIPAY_PRIVATE_KEY=
ALIPAY_PUBLIC_KEY=
ALIPAY_NOTIFY_URL=https://你的域名/payment/alipay_notify
PAYMENT_PUBLIC_BASE_URL=https://你的域名
```

为兼容旧部署，`APP_PRIVATE_KEY` 仍可代替 `ALIPAY_PRIVATE_KEY`。

## 上线步骤

1. 配置上述生产环境变量，不要把真实密钥提交到 Git。
2. 执行 `flask --app run.py db upgrade`，为充值订单增加支付渠道字段。
3. 确认支付平台后台允许相应的异步通知地址。
4. 使用最低金额套餐完成一次真实支付，检查后台订单状态、用户积分和通知是否只增加一次。
