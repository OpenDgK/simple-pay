# Simple Order Pay

极简匿名商品支付站点。用户不需要注册，选择商品并填写邮箱后直接打开支付窗口；后端支持 mock、艺爪付费、虎皮椒、支付宝官方电脑网站支付和 DaxPay 支付；管理员可维护账号密码库存，支付成功后自动分配账号、写入交付结果并发送邮件；用户通过订单号 + 查询码或 token 链接查看交付结果。

## 技术栈

- Frontend：静态 HTML/CSS/JavaScript，Nginx 容器托管。
- Backend：FastAPI。
- Database：独立 MySQL 8.4 容器，数据库名默认 `simple_order_pay`。
- Deployment：Docker Compose + 宿主机 Nginx 反向代理。

宿主机只绑定 `127.0.0.1:3001` 和 `127.0.0.1:8001`，外部访问仍走服务器已有的 80/443。MySQL 只在 Docker 内部网络开放，不占用宿主机数据库端口。

## 目录结构

```text
simple-order-pay/
|-- backend/                     FastAPI 后端
|   |-- app/
|   |   |-- main.py              API 路由
|   |   |-- alipay.py            支付宝签名、下单、回调验签
|   |   |-- daxpay.py            DaxPay 签名、下单、回调校验
|   |   |-- models.py            SQLAlchemy 模型
|   |   |-- security.py          查询码/admin token 工具
|   |   `-- config.py            环境变量配置
|   |-- Dockerfile
|   `-- requirements.txt
|-- frontend/                    静态前端
|   |-- public/
|   |   |-- index.html
|   |   |-- styles.css
|   |   `-- app.js
|   |-- Dockerfile
|   `-- nginx.conf
|-- db/schema.sql                数据库表结构参考
|-- nginx/simple-order-pay.conf.template
|-- scripts/deploy.sh            一键部署
|-- scripts/backup.sh            一键备份
|-- scripts/stop.sh              停止/可选卸载
|-- docker-compose.yml
|-- .env.example
`-- README.md
```

## 本地启动

```bash
cd simple-order-pay
cp .env.example .env
```

编辑 `.env`，至少修改：

```env
PUBLIC_BASE_URL=http://127.0.0.1:3001
DOMAIN_NAME=127.0.0.1
APP_SECRET=一段随机长字符串
ADMIN_PASSWORD=强密码
MYSQL_PASSWORD=随机密码
MYSQL_ROOT_PASSWORD=随机密码
PAYMENT_MODE=mock
```

启动：

```bash
docker compose up -d --build
```

访问：

- 前端：http://127.0.0.1:3001
- 后端健康检查：http://127.0.0.1:8001/api/health
- 后台默认路径：http://127.0.0.1:3001/ops-7q4-panel

mock 模式下，下单后页面会显示“模拟支付成功”按钮，可以完整测试 paid 状态和交付查询。

## 服务器部署

推荐目标目录：

```bash
sudo mkdir -p /opt/simple-order-pay
sudo rsync -a ./simple-order-pay/ /opt/simple-order-pay/
cd /opt/simple-order-pay
sudo cp .env.example .env
sudo nano .env
```

生产环境至少修改：

```env
PUBLIC_BASE_URL=https://你的域名
DOMAIN_NAME=你的域名
APP_SECRET=openssl rand -hex 32 生成的值
ADMIN_USERNAME=admin
ADMIN_PASSWORD=强密码
MYSQL_PASSWORD=强随机密码
MYSQL_ROOT_PASSWORD=强随机密码
PAYMENT_MODE=mock
```

运行部署脚本：

```bash
sudo bash scripts/deploy.sh
```

脚本会：

- 检查 Docker、Docker Compose、Nginx。
- 当 `.env` 不存在时，从 `.env.example` 创建并自动生成 `APP_SECRET`、`ADMIN_PASSWORD`、MySQL 密码。
- 检查 `FRONTEND_HOST_PORT` 和 `BACKEND_HOST_PORT` 是否冲突。
- 构建并启动独立 Docker Compose 项目。
- 只新增或更新 `/etc/nginx/conf.d/simple-order-pay.conf`，不会覆盖其他 Nginx 配置。
- 执行 `nginx -t` 并 reload Nginx。

如果该站点配置已存在，脚本默认不覆盖。确实需要重写该文件时：

```bash
sudo FORCE_NGINX=1 bash scripts/deploy.sh
```

## 配置域名

1. 在 DNS 服务商添加 A 记录，把 `DOMAIN_NAME` 指向服务器公网 IP。
2. 在 `.env` 设置：

```env
DOMAIN_NAME=pay.example.com
PUBLIC_BASE_URL=https://pay.example.com
DAXPAY_NOTIFY_URL=https://pay.example.com/api/payments/daxpay/notify
DAXPAY_RETURN_URL=https://pay.example.com/
```

3. 重新部署或重载 Nginx：

```bash
cd /opt/simple-order-pay
sudo FORCE_NGINX=1 bash scripts/deploy.sh
```

## Nginx 配置

模板位于：

```text
nginx/simple-order-pay.conf.template
```

生成后的站点文件：

```text
/etc/nginx/conf.d/simple-order-pay.conf
```

核心反代关系：

```nginx
location /api/  -> http://127.0.0.1:8001
location /      -> http://127.0.0.1:3001
```

这个项目不会修改 `/etc/nginx/nginx.conf`，也不会删除或覆盖服务器已有站点配置。

## 配置 HTTPS

如果服务器使用 Certbot：

```bash
sudo certbot --nginx -d pay.example.com
```

执行前确认：

```bash
sudo nginx -t
curl -I http://pay.example.com
```

Certbot 会基于新增站点配置追加 TLS server block。不要手动覆盖其他项目的 HTTPS 配置。

## 配置支付宝

默认使用 mock 模式：

```env
PAYMENT_MODE=mock
```

接入支付宝官方电脑网站支付时改为：

```env
PAYMENT_MODE=alipay
ALIPAY_GATEWAY_URL=https://openapi.alipay.com/gateway.do
ALIPAY_APP_ID=你的支付宝应用 AppID
ALIPAY_APP_PRIVATE_KEY=你的应用私钥
ALIPAY_PUBLIC_KEY=支付宝公钥
ALIPAY_NOTIFY_URL=https://你的域名/api/payments/alipay/notify
ALIPAY_RETURN_URL=https://你的域名/
ALIPAY_SIGN_TYPE=RSA2
ALIPAY_PAGE_PAY_PRODUCT_CODE=FAST_INSTANT_TRADE_PAY
```

后端封装在 `backend/app/alipay.py`：

- 创建支付订单：`alipay.trade.page.pay`
- 业务订单号：`out_trade_no`
- 回调入口：`/api/payments/alipay/notify`
- 回调会校验支付宝 `sign`、`app_id` 和订单金额。
- 回调中的 `TRADE_SUCCESS` 或 `TRADE_FINISHED` 会把订单状态更新为 `paid`。

如果先用支付宝沙箱测试，把 `ALIPAY_GATEWAY_URL` 改为沙箱网关，并填写沙箱应用的 AppID、应用私钥和支付宝公钥。

## 配置 DaxPay

默认使用 mock 模式：

```env
PAYMENT_MODE=mock
```

接入真实 DaxPay 时改为：

```env
PAYMENT_MODE=daxpay
DAXPAY_API_URL=https://你的-daxpay-网关
DAXPAY_APP_ID=你的应用号
DAXPAY_MCH_NO=你的商户号
DAXPAY_SIGN_SECRET=你的签名密钥
DAXPAY_NOTIFY_URL=https://你的域名/api/payments/daxpay/notify
DAXPAY_RETURN_URL=https://你的域名/
DAXPAY_SIGN_TYPE=HMAC_SHA256
DAXPAY_CHANNEL=wechat_pay
DAXPAY_METHOD=qrcode
```

后端封装在 `backend/app/daxpay.py`：

- 创建支付订单：`POST {DAXPAY_API_URL}/unipay/pay`
- 业务订单号：`bizOrderNo`
- 回调入口：`/api/payments/daxpay/notify`
- 回调会校验 `sign`，校验失败返回 400。
- 回调中的状态匹配 `pay_success/success/paid` 时，订单状态更新为 `paid`。

不同 DaxPay 版本、网关路径或字段名可能有差异，上线前请用你的 DaxPay 实例接口文档核对 `channel`、`method`、返回 `payBody` 的展示方式和回调 payload。

## 配置虎皮椒支付

虎皮椒也叫 XunhuPay。本项目已预留独立支付模式：

```env
PAYMENT_MODE=xunhupay
XUNHUPAY_GATEWAY_URL=https://api.xunhupay.com/payment/do.html
XUNHUPAY_APP_ID=你的虎皮椒APPID
XUNHUPAY_APP_SECRET=你的虎皮椒APPSECRET
XUNHUPAY_NOTIFY_URL=https://你的域名/api/payments/xunhupay/notify
XUNHUPAY_RETURN_URL=https://你的域名/
XUNHUPAY_VERSION=1.1
XUNHUPAY_PLUGINS=simple-order-pay
```

后台入口通常在虎皮椒商户后台的“支付渠道管理 / 我的支付渠道”里查看 `APPID` 和 `APPSECRET`。发起支付域名填用户实际打开购买页面的域名，例如 `pay.example.com`。

后端封装在 `backend/app/xunhupay.py`：

- 创建支付订单：`POST https://api.xunhupay.com/payment/do.html`
- 业务订单号：`trade_order_id`
- 回调入口：`/api/payments/xunhupay/notify`
- 签名字段：`hash`
- 回调验签失败返回 `fail` 和 400。
- 回调状态 `OD` 会把订单状态更新为 `paid`，然后自动扣库存、写入交付结果并发送邮件。
- 回调成功后返回纯文本 `success`。

真实支付必须使用公网 HTTPS 回调地址，本地 `127.0.0.1` 无法接收虎皮椒服务器回调。本地开发继续使用 `PAYMENT_MODE=mock`。

## 配置人工确认收款

如果你想使用自己的支付宝/微信收款码，并且不想让用户填写支付宝订单号，可以使用人工确认模式：

1. 用户在本站选择商品并填写邮箱。
2. 前台直接展示你的收款码、订单号、查询码和金额。
3. 用户付款后点击“我已付款，等待确认”。
4. 订单支付状态变为 `reviewing`，库存继续锁定。
5. 管理员后台核对到账后，把支付状态改为 `paid` 并保存。
6. 系统自动扣库存、写入交付结果并发送账号密码邮件。

`.env` 示例：

```env
PAYMENT_MODE=manual
MANUAL_PAYMENT_QR_URL=https://你的域名/path/to/pay-qr.png
MANUAL_PAYMENT_INSTRUCTIONS=请扫码付款，付款后点击“我已付款，等待确认”。管理员确认到账后会自动发货。
```

这种模式没有支付平台自动回调，所以不要在后台确认到账前把订单改为 `paid`。

## 配置艺爪付费

艺爪付费 API 文档入口：https://www.ezboti.com/docs/revenue/api/

它不是传统的 `notify_url` 支付网关，而是托管付费页面和权益查询 API。本项目接入方式是：

1. 用户在本站下单，系统生成订单并锁定一条库存。
2. 后端用 `customer.info` 创建或查询艺爪客户，并拿到 `home_link.url`。
3. 前端直接弹出艺爪付费页面，用户在新窗口付款。
4. 本站自动轮询 `customer.info`，用户也可以点击“我已完成支付，立即检查”。
5. 后端检测 `balance_s` 里是否有已付费且可用的权益。
6. 检测成功后订单变成 `paid`，系统自动扣库存、写交付结果并发送邮件。

用户不需要填写支付宝订单号。只有当你在艺爪后台使用“人工核对交易单号”的简易收款流程、并且 API 不返回可确认的权益状态时，系统才无法做到全自动确认；这种情况下建议改用虎皮椒、支付宝官方支付或 DaxPay 这类有回调的网关。

库存会在创建待支付订单时短暂锁定，避免 1 个账号被多个人同时付款购买。用户关闭艺爪支付窗口且未检测到付款时，前端会调用取消接口释放库存；如果用户直接关闭本站页面，库存会在 `INVENTORY_RESERVATION_MINUTES` 到期后自动释放。

艺爪付费墙的真实扣款价格在艺爪后台配置。本站后台的商品价格只负责前台展示，请保持两边一致；如果希望“本站后台价格就是真实扣款价格”，需要改用支持后端创建指定金额订单的支付网关。

`.env` 示例：

```env
PAYMENT_MODE=ezboti
EZBOTI_API_URL=https://revenue.ezboti.com/api/v1/server
EZBOTI_PROJECT_ID=你的项目ID
EZBOTI_PROJECT_SECRET=你的项目密钥
EZBOTI_PAYWALL_ID=你的付费墙ID
EZBOTI_PAYWALL_ALIAS=
EZBOTI_EQUITY_ID=
EZBOTI_EQUITY_ALIAS=
EZBOTI_REQUIRE_CHARGED=true
EZBOTI_REQUIRE_USABLE=true
```

`PROJECT_ID` 和 `PROJECT_SECRET` 在艺爪项目后台 API/开发配置里获取；`PAYWALL_ID` 或 `PAYWALL_ALIAS` 在付费墙配置里获取。多商品场景建议在艺爪后台给不同商品配置明确权益，并在本站配置 `EZBOTI_EQUITY_ID` 或 `EZBOTI_EQUITY_ALIAS`，避免用户购买了不对应的权益也触发发货。

后端封装在 `backend/app/ezboti.py`，公开同步接口是：

```text
POST /api/payments/ezboti/sync/{order_no}?query_code=...
POST /api/orders/{order_no}/cancel?query_code=...
```

## 管理后台

默认后台路径：

```text
/ops-7q4-panel
```

可以通过 `.env` 修改：

```env
ADMIN_PANEL_PATH=/ops-7q4-panel
ADMIN_API_PREFIX=/api/order-ops-7q4
```

后台功能：

- 查看订单号、邮箱、商品、支付状态、交付状态。
- 手动填写交付结果。
- 修改支付状态：`pending`、`reviewing`、`paid`、`failed`。人工确认收款时，确认到账后改为 `paid` 会自动发货并发送邮件。
- 修改交付状态：`pending`、`processing`、`delivered`、`cancelled`。
- 配置多个商品、每个商品的价格、是否前台展示和排序。
- 批量导入账号库存；每行一个账号和密码。
- 修改首页卖点、流程、查询区和购买说明文案。

## 账号库存和自动发货

后台“账号库存”按商品管理账号和密码。前台只显示库存数量，不显示具体账号：

- 库存为 0 时，商品会显示“售罄”，用户不能提交支付。
- 用户下单时，系统会先占用一条库存，默认占用 `30` 分钟。
- 支付成功后，库存标记为 `sold`，订单自动写入交付结果。
- 如果 SMTP 已配置，系统会把账号和密码发送到用户填写的邮箱。
- 如果 SMTP 未配置或发送失败，支付和交付仍会完成，后台订单里会显示邮件错误。

批量导入格式支持以下几种，每行一条：

```text
account1 password1
account2,password2
account3----password3
account4|password4
```

库存占用时间可在 `.env` 中调整：

```env
INVENTORY_RESERVATION_MINUTES=30
```

邮件发送配置：

```env
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的邮箱
SMTP_PASSWORD=邮箱 SMTP 授权码
SMTP_FROM=你的邮箱
SMTP_FROM_NAME=Simple Order Pay
SMTP_USE_SSL=true
SMTP_USE_TLS=false
```

QQ、网易、企业邮箱通常要填写“SMTP 授权码”，不是登录密码。

## 用户查询

下单成功后，系统返回：

- 订单号
- 查询码
- token 查询链接

用户可通过首页“查询交付”输入订单号 + 查询码，也可直接打开 token 链接：

```text
https://你的域名/order/<token>
```

查询码和 token 在数据库中只保存 SHA-256 hash。

## 上传限制

当前前台默认只开放“商品 + 邮箱”下单，不展示需求描述、备注和上传文件字段。后端仍保留上传能力，方便以后需要附件下单时重新启用。

`.env` 中配置：

```env
MAX_UPLOAD_MB=20
ALLOWED_UPLOAD_EXTENSIONS=.jpg,.jpeg,.png,.pdf,.doc,.docx,.xls,.xlsx,.zip,.txt
ALLOWED_UPLOAD_MIME_PREFIXES=image/,application/pdf,application/zip,application/vnd,application/msword,text/plain
```

上传文件保存在独立 Docker volume：

```text
simple-order-pay-uploads
```

文件不通过 Nginx 静态目录公开，只能由管理员登录后下载。

## 查看日志

```bash
cd /opt/simple-order-pay
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f mysql
```

查看最近 200 行：

```bash
docker compose logs --tail=200 backend
```

## 备份数据库和上传文件

```bash
cd /opt/simple-order-pay
sudo bash scripts/backup.sh
```

默认输出：

```text
/opt/simple-order-pay/backups/YYYYmmdd_HHMMSS/
|-- simple_order_pay.sql
|-- uploads.tar.gz
`-- env.copy
```

`env.copy` 包含敏感配置，脚本会设置为 `600` 权限，请妥善保管。

## 停止和卸载

停止容器但保留数据：

```bash
cd /opt/simple-order-pay
sudo bash scripts/stop.sh
```

同时移除这个项目的 Nginx 站点配置：

```bash
sudo REMOVE_NGINX_CONF=1 bash scripts/stop.sh
```

确认要删除 MySQL 和上传文件 volume 时：

```bash
sudo CONFIRM_REMOVE_DATA=yes-remove-simple-order-pay-data bash scripts/stop.sh
```

同时删除站点配置和数据：

```bash
sudo REMOVE_NGINX_CONF=1 CONFIRM_REMOVE_DATA=yes-remove-simple-order-pay-data bash scripts/stop.sh
```

脚本只操作本项目的 Compose 服务、命名 volume 和 `/etc/nginx/conf.d/simple-order-pay.conf`，不会删除 `/var/www`、`/etc/nginx` 或 `/opt` 下其他项目。

## 数据库表

核心表：

- `orders`：订单、联系方式、商品快照、附件元信息、支付状态、交付状态、交付结果。
- `products`：后台可配置商品、价格、币种、排序和展示状态。
- `inventory_items`：账号库存、库存状态、关联订单和售出时间。
- `app_settings`：后台可配置的前台文案。
- `payment_events`：支付回调或 mock 支付事件日志。

完整参考见：

```text
db/schema.sql
```

应用启动时会通过 SQLAlchemy 自动建表。

## 常用 API

公开：

- `GET /api/health`
- `GET /api/config`
- `POST /api/orders`
- `GET /api/orders/lookup?order_no=...&query_code=...`
- `GET /api/orders/token/{token}`
- `POST /api/payments/alipay/notify`
- `POST /api/payments/daxpay/notify`
- `POST /api/payments/xunhupay/notify`
- `POST /api/payments/ezboti/sync/{order_no}?query_code=...`
- `POST /api/payments/manual/{order_no}?query_code=...`
- `POST /api/payments/mock/{order_no}?query_code=...`
- `POST /api/orders/{order_no}/cancel?query_code=...`

后台：

- `POST {ADMIN_API_PREFIX}/login`
- `GET {ADMIN_API_PREFIX}/orders`
- `GET {ADMIN_API_PREFIX}/orders/{order_no}`
- `PATCH {ADMIN_API_PREFIX}/orders/{order_no}/delivery`
- `GET {ADMIN_API_PREFIX}/orders/{order_no}/file`
- `GET {ADMIN_API_PREFIX}/products`
- `POST {ADMIN_API_PREFIX}/products`
- `PATCH {ADMIN_API_PREFIX}/products/{product_id}`
- `GET {ADMIN_API_PREFIX}/inventory`
- `POST {ADMIN_API_PREFIX}/inventory`
- `POST {ADMIN_API_PREFIX}/inventory/bulk`
- `PATCH {ADMIN_API_PREFIX}/inventory/{item_id}`
- `DELETE {ADMIN_API_PREFIX}/inventory/{item_id}`
- `GET {ADMIN_API_PREFIX}/content`
- `PUT {ADMIN_API_PREFIX}/content`

## 部署前检查清单

- `.env` 中 `ADMIN_PASSWORD` 已改为强密码。
- `.env` 中 `APP_SECRET`、`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD` 已改为随机强值。
- `DOMAIN_NAME` 和 `PUBLIC_BASE_URL` 指向正确域名。
- `FRONTEND_HOST_PORT`、`BACKEND_HOST_PORT` 未与其他项目冲突。
- Nginx 只新增 `/etc/nginx/conf.d/simple-order-pay.conf`。
- HTTPS 证书已配置。
- 虎皮椒、支付宝或 DaxPay 商户配置、签名方式和回调地址已在对应后台核对。

## 协作开发上手指南

本项目建议作为一个独立商城项目管理，推荐单独创建 GitHub 仓库，例如 `simple-order-pay`。不要把服务器上的 `.env`、数据库、上传文件、日志和备份提交到 Git。

本项目当前协作信息：

```text
GitHub: git@github.com:OpenDgK/simple-pay.git
计划域名: pay.yingkai.shop
计划服务器: 149.28.78.223
生产部署目录: /opt/simple-order-pay
```

支付方式当前还没有最终确定。代码已经预留 `mock`、`xunhupay`、`alipay`、`daxpay` 四种模式；新员工主要任务可以从支付接入开始，本地开发时先保持 `PAYMENT_MODE=mock`。

### 项目边界

- 本项目只放在 `simple-order-pay/` 目录内。
- 服务器部署目录固定建议使用 `/opt/simple-order-pay`。
- Docker Compose 项目名、容器、volume 都只属于本项目。
- Nginx 只新增 `/etc/nginx/conf.d/simple-order-pay.conf`，不要修改服务器已有站点配置。
- 前端本地端口默认 `3001`，后端本地端口默认 `8001`，生产环境由 Nginx 通过 80/443 反向代理。
- MySQL 使用独立容器和独立数据库 `simple_order_pay`，不要连接或改动服务器上其他项目的数据库。

### 新员工第一次上手

1. 克隆仓库：

```bash
git clone git@github.com:OpenDgK/simple-pay.git
cd simple-order-pay
```

如果还没有配置 GitHub SSH key，也可以先用 HTTPS 克隆：

```bash
git clone https://github.com/OpenDgK/simple-pay.git
cd simple-order-pay
```

2. 创建本地配置：

```bash
cp .env.example .env
```

3. 修改 `.env`，本地开发建议保持：

```env
PUBLIC_BASE_URL=http://127.0.0.1:3001
DOMAIN_NAME=127.0.0.1
PAYMENT_MODE=mock
```

同时把这些密码改成自己的本地随机值：

```env
APP_SECRET=本地随机长字符串
ADMIN_PASSWORD=本地后台密码
MYSQL_PASSWORD=本地数据库密码
MYSQL_ROOT_PASSWORD=本地数据库root密码
```

4. 启动项目：

```bash
docker compose up -d --build
```

5. 打开页面：

```text
前台：http://127.0.0.1:3001
后台：http://127.0.0.1:3001/ops-7q4-panel
健康检查：http://127.0.0.1:8001/api/health
```

6. 本地测试流程：

- 登录后台。
- 新增或编辑商品。
- 在“账号库存”里给商品添加测试账号和密码。
- 回到前台下单。
- mock 支付成功。
- 检查订单是否变成 `paid` 和 `delivered`。
- 如果配置了 SMTP，检查用户邮箱是否收到账号密码。

### 开发分工建议

- 一个人负责支付接入，例如虎皮椒、支付宝、DaxPay。
- 一个人负责前端页面、后台表单和交互。
- 一个人负责部署脚本、README、服务器备份和日志检查。

每个功能开一个独立分支：

```bash
git switch -c feature/xunhupay-payment
git switch -c feature/admin-inventory-ui
git switch -c feature/deploy-docs
```

开发完成后提交 Pull Request，由负责人检查后再合并到 `main`。

### 不要提交的内容

这些内容必须留在本机或服务器，不要提交到 GitHub：

- `.env`
- `.local-logs/`
- `backups/`
- `uploads/`
- `local_uploads/`
- `*.log`
- 本地数据库文件
- 真实支付密钥
- 邮箱 SMTP 密码
- 管理员真实密码

`.env.example` 可以提交，但里面只能放占位符，不能放真实密钥。

### 本地和远程如何保持一致

代码保持一致，配置分开管理：

```text
本地：代码相同，.env 使用 mock 支付、本地地址、本地密码
远程：代码相同，.env 使用真实域名、真实支付、真实邮箱、强密码
```

也就是说，员工开发时只改代码和 `.env.example` 的字段说明，不要把服务器 `.env` 下载后提交。

### 远程部署流程

远程服务器只部署 `main` 分支确认过的代码：

```bash
cd /opt/simple-order-pay
git pull --ff-only
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
```

如果首次部署：

```bash
sudo mkdir -p /opt/simple-order-pay
cd /opt/simple-order-pay
git clone git@github.com:OpenDgK/simple-pay.git .
cp .env.example .env
nano .env
sudo bash scripts/deploy.sh
```

部署前必须确认：

- 域名 DNS 已指向服务器。
- `.env` 里的 `PUBLIC_BASE_URL` 是真实 HTTPS 域名。
- 支付回调地址是公网 HTTPS 地址。
- SMTP 发信已测试通过。
- 端口 `3001` 和 `8001` 没有被服务器其他项目占用。

### 给新员工的安全规则

- 不要执行 `rm -rf /opt`、`rm -rf /var/www`、`rm -rf /etc/nginx`。
- 不要修改服务器其他项目的 Nginx 配置。
- 不要把 `.env`、支付密钥、邮箱密码发到群里或提交到 GitHub。
- 不要直接在服务器上改代码后忘记提交，所有正式改动都要回到 Git 分支里。
- 不确定时先在本地 `PAYMENT_MODE=mock` 测试，再让负责人部署到远程。

### 当前待办

- 确定最终支付渠道。
- 继续完善虎皮椒或其他支付渠道的真实商户联调。
- 完成真实支付回调验签测试。
- 远程服务器配置 HTTPS 域名。
- 远程 `.env` 配置阿里云 SMTP。
- 生产环境支付成功后测试自动发货邮件。
