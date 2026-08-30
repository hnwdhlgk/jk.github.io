# Telegram 关键词监控机器人

实时监听群组消息，命中预设关键词时自动提醒并记录。

## 功能

- 🔔 **关键词监控**：群内消息命中关键词时自动回复提醒
- 📤 **消息转发**：命中后可将原始消息转发到指定私聊或另一个群组
- 🌐 **Web 管理后台**：通过浏览器管理关键词、转发配置、查看命中记录
- ➕ **动态管理**：通过命令或 Web 后台增删关键词，无需改代码
- 📊 **命中记录**：自动记录每次命中（时间、关键词、发送者、内容摘要）
- 🔒 **权限控制**：仅群组管理员可增删关键词和清空记录；Web 后台需密码登录
- 💾 **数据持久化**：关键词和历史记录保存在 JSON 文件，重启不丢失
- 👥 **多群组独立**：每个群组的关键词和记录互相隔离

## 快速开始

### 1. 创建 Telegram 机器人

1. 在 Telegram 中搜索 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`，按提示设置机器人名称和用户名
3. 复制获得的 **Bot Token**

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置并启动

```bash
export TELEGRAM_BOT_TOKEN="你的Bot Token"
python bot.py
```

看到 `机器人启动中...` 即表示运行成功。

### 4. 加入群组并使用

1. 把机器人拉入你的群组
2. **将机器人设为群组管理员**（否则可能无法读取消息）
3. 在群内发送 `/add 优惠活动` 添加关键词
4. 之后群内任何消息包含"优惠活动"时，机器人会自动提醒

## 命令列表

| 命令 | 说明 | 权限 |
|------|------|------|
| `/start` | 查看帮助信息 | 所有人 |
| `/add <关键词>` | 添加监控关键词 | 管理员 |
| `/remove <关键词>` | 删除监控关键词 | 管理员 |
| `/list` | 查看当前关键词列表 | 所有人 |
| `/history` | 查看最近命中记录 | 所有人 |
| `/clear` | 清空命中记录 | 管理员 |
| `/getid` | 获取当前聊天的 ID（用于设置转发目标） | 所有人 |
| `/set_forward <聊天ID>` | 设置命中后转发的目标聊天 | 管理员 |
| `/forward_info` | 查看当前转发配置 | 所有人 |
| `/clear_forward` | 清除转发目标 | 管理员 |

## 转发功能使用说明

命中关键词后，除了在原群组回复提醒，还可以将原始消息转发到你指定的私聊或另一个群组。

### 设置步骤

1. **获取目标聊天 ID**
   - 转发到私聊：在你和机器人的私聊窗口中发送 `/getid`，复制返回的 ID
   - 转发到另一个群组：把机器人也拉入目标群组并设为管理员，在该群发送 `/getid`，复制返回的 ID（群组 ID 通常以 `-` 开头，如 `-1001234567890`）

2. **在监控群组中设置转发目标**
   ```
   /set_forward -1001234567890
   ```
   机器人会自动向目标聊天发送一条测试消息（随后自动删除），确认可以正常访问。

3. **验证配置**
   ```
   /forward_info
   ```

4. **取消转发**
   ```
   /clear_forward
   ```

### 转发效果

命中关键词时，目标聊天会收到：
- 一条通知消息（包含命中关键词、发送者、来源群组、时间）
- 原始消息的完整转发

### 注意事项

- 机器人必须在目标聊天中存在且有发消息权限
- 如果目标是私聊，你需要先给机器人发过任意消息（Telegram 限制机器人无法主动发起私聊）
- 转发失败时会在原群组提示，但不影响正常的提醒和记录功能

## 配置环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | （必填） | 机器人 Token |
| `BOT_DATA_FILE` | `bot_data.json` | 数据存储文件路径 |
| `WEB_ENABLED` | `1` | 是否启用 Web 管理后台（设为 `0` 禁用） |
| `WEB_HOST` | `0.0.0.0` | Web 后台监听地址 |
| `WEB_PORT` | `8080` | Web 后台监听端口 |
| `ADMIN_PASSWORD` | （自动生成） | Web 后台登录密码，未设置时启动时自动生成并打印 |
| `FLASK_SECRET_KEY` | （自动生成） | Flask session 加密密钥，生产环境建议固定 |

## Web 管理后台

启动机器人后，Web 管理后台默认在 `http://localhost:8080` 运行。

### 登录

1. 打开浏览器访问 `http://你的服务器IP:8080`
2. 输入管理员密码登录
   - 如果设置了 `ADMIN_PASSWORD` 环境变量，使用该密码
   - 如果未设置，启动时会在控制台自动生成并打印一个随机密码

### 功能页面

**群组列表页**（首页）
- 查看所有已配置的监控群组（名称、ID、关键词数量、命中记录数、转发状态、最近命中时间）
- 手动添加新群组（输入群组 ID 和可选名称）
- 机器人加入群组并收到消息后，群体会自动出现在列表中

**群组详情页**
- **关键词管理**：查看所有监控关键词，一键添加或删除
- **转发配置**：设置/查看/清除消息转发目标聊天 ID
- **命中记录**：查看最近 50 条命中记录（时间、关键词、发送者、内容预览），可一键清空

### 安全建议

- 生产环境务必设置 `ADMIN_PASSWORD` 为强密码
- 建议通过 Nginx 反向代理并配置 HTTPS
- 如不需要 Web 后台，设置 `WEB_ENABLED=0` 禁用

## 部署到 GitHub + 云平台

GitHub 仓库本身不能 24/7 运行长期服务，但可以**代码托管在 GitHub，自动部署到支持长期运行的云平台**。项目已内置 Dockerfile 和 render.yaml，支持一键部署。

### 方案一：Render（推荐，免费套餐）

Render 支持从 GitHub 仓库自动构建和部署，免费套餐可用。

#### 第一步：推送到 GitHub

```bash
# 在项目目录中初始化 git（如果还没有）
cd telegram-keyword-bot
git init
git add .
git commit -m "Initial commit: Telegram keyword monitor bot"

# 在 GitHub 上创建新仓库后，推送代码
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

#### 第二步：一键部署到 Render

1. 登录 [Render.com](https://render.com)（可用 GitHub 账号登录）
2. 点击右上角 **New +** → **Blueprint**
3. 连接你刚才创建的 GitHub 仓库
4. Render 会自动读取 `render.yaml`，显示服务配置
5. 点击 **Apply** 开始部署

#### 第三步：配置环境变量

部署后在 Render 服务页面 → **Environment** 中设置：

| 变量 | 值 |
|------|-----|
| `TELEGRAM_BOT_TOKEN` | 从 @BotFather 获取的机器人 Token |
| `ADMIN_PASSWORD` | 你想设置的 Web 后台密码 |

设置后 Render 会自动重新部署。

#### 第四步：访问 Web 后台

部署完成后，Render 会给你一个域名（如 `https://telegram-keyword-bot-xxxx.onrender.com`），访问该域名即可登录 Web 管理后台。

#### 免费套餐保活（重要）

Render 免费实例在 **15 分钟无入站流量后会休眠**，休眠后 bot 停止接收消息。解决方法：

1. 注册 [UptimeRobot](https://uptimerobot.com/)（免费）
2. 添加一个 Monitor，类型选 **HTTP(s)**
3. URL 填你的 Render 域名 + `/login`（如 `https://xxx.onrender.com/login`）
4. 监控间隔设为 **5 分钟**

这样 UptimeRobot 会定期 ping 你的服务，保持实例唤醒。

### 方案二：Railway

[Railway](https://railway.app) 提供每月 $5 免费额度，实例不会休眠，更适合 bot 运行。

1. 登录 Railway，点击 **New Project** → **Deploy from GitHub repo**
2. 选择你的仓库，Railway 自动识别 Dockerfile
3. 在 **Variables** 中添加 `TELEGRAM_BOT_TOKEN` 和 `ADMIN_PASSWORD`
4. 点击 **Deploy**

### 方案三：Replit

[Replit](https://replit.com) 可以直接导入 GitHub 仓库运行，免费版会休眠但可配合保活服务。

1. Replit 中点击 **Create** → **Import from GitHub**
2. 选择你的仓库
3. 在 **Secrets** 中添加环境变量
4. Run 命令填 `python bot.py`

### 方案四：自托管服务器（VPS）

如果你有自己的服务器，最稳定可靠：

```bash
# 克隆代码
git clone https://github.com/你的用户名/你的仓库名.git
cd 你的仓库名

# 安装依赖
pip install -r requirements.txt

# 设置环境变量并启动
export TELEGRAM_BOT_TOKEN="你的Token"
export ADMIN_PASSWORD="你的密码"
python bot.py
```

建议用 systemd 或 Docker 管理进程，开机自启。

### Docker 本地运行

项目内置 Dockerfile，也可以直接用 Docker 本地运行：

```bash
docker build -t telegram-keyword-bot .
docker run -d \
  --name telegram-bot \
  -p 8080:8080 \
  -e TELEGRAM_BOT_TOKEN="你的Token" \
  -e ADMIN_PASSWORD="你的密码" \
  -v $(pwd)/data:/app/data \
  telegram-keyword-bot
```

### 数据持久化说明

- 关键词配置和命中记录保存在 `bot_data.json`
- Render 免费套餐**不支持持久化磁盘**，实例重启或重新部署后数据会丢失
- 需要数据持久化时：
  - Render 升级到 Starter 套餐（$7/月），在 `render.yaml` 中取消 disk 配置的注释
  - 使用 Railway / 自托管等支持持久存储的平台
  - 或定期通过 Web 后台记录关键词配置，重新部署后手动重新添加

## 后台运行（可选）

使用 systemd 或 nohup 保持运行：

```bash
nohup python bot.py > bot.log 2>&1 &
```

## 注意事项

- Telegram 隐私设置：机器人默认无法读取非命令消息，**必须将机器人设为群组管理员**才能正常监控
- 关键词匹配不区分大小写
- 每个群组最多保留 200 条命中记录，超出自动清理最旧的
- 数据文件 `bot_data.json` 会在程序运行目录自动创建
