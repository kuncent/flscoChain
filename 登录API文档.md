# 跨专业综合实训平台 API 文档

> **基础地址**： https://ecosim.sztzjy.com:166/server 
> **认证方式**：登录后返回的 Token 放在请求头 `Authorization: Bearer {token}`
> **Token 有效期**：12 小时

---

## 接口一览

| 序号 | 接口名称 | 请求方式 | 路径 | 是否需要Token |
|------|---------|---------|------|--------------|
| 1 | 明文密码加密 | GET | /api/user/encrypt` | 否 |
| 2 | 用户登录 | POST | `/api/user/login` | 否 |
| 3 | 生成智云登录Token | GET | `/api/user/generateZhiYunToken` | 否 |

---

## 1. 明文密码加密

将明文密码使用 RSA 公钥加密，返回加密后的密文，用于登录接口的 `passwordEncode` 参数。

### 请求说明

| 项目 | 内容 |
|------|------|
| 请求方式 | GET |
| 请求路径 | `/api/user/encrypt` |
| 是否需要Token | 否 |

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `pwd` | String | 是 | 明文密码 |

### 请求示例

```
GET /server/api/user/encrypt?pwd=123456
```

### 成功返回

```json
{
  "code": 200,
  "msg": "加密成功",
  "data": "Bs+MJo8yrGxvwD/G5QGTihU6lh/PjaDKQNxBDs66GQrNXoX0..."
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | Integer | 状态码，200 表示成功 |
| `msg` | String | 提示信息 |
| `data` | String | RSA 公钥加密后的密码密文（Base64编码） |

### 错误返回

```json
{
  "code": 500,
  "msg": "异常信息",
  "data": null
}
```

---

## 2. 用户登录

支持两种登录方式：
- **账号密码登录**：传入学号和 RSA 加密后的密码
- **智云 SSO 登录**：传入智云平台的 Token，自动校验并登录

登录成功后返回系统的 JWT Token，后续所有需要认证的接口都需在请求头携带该 Token。

### 请求说明

| 项目 | 内容 |
|------|------|
| 请求方式 | POST |
| 请求路径 | `/api/user/login` |
| 是否需要Token | 否 |
| Content-Type | `application/x-www-form-urlencoded` |

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `username` | String | 是 | 用户名/学号 |
| `passwordEncode` | String | 条件必填 | RSA 公钥加密后的密码密文（账号密码登录时必填，可通过接口1获取） |
| `TOKEN` | String | 条件必填 | 智云平台 Token（SSO 登录时必填，可通过接口3生成） |

> 两种登录方式二选一：传 `TOKEN` 走 SSO 登录，不传 `TOKEN` 则走账号密码登录（此时 `passwordEncode` 必填）。

### 请求示例

**账号密码登录：**

```
POST /server/api/user/login
Content-Type: application/x-www-form-urlencoded

username=2024001&passwordEncode=Bs+MJo8yrGxvwD/G5QGTihU6lh/PjaDKQNxBDs66GQrNXoX0...
```

**智云 SSO 登录：**

```
POST /server/api/user/login
Content-Type: application/x-www-form-urlencoded

TOKEN=eyJhbGciOiJIUzI1NiJ9.eyJ1c2VybmFtZSI6IjIwMjQwMDEifQ...
```

### 成功返回

```json
{
  "code": 200,
  "msg": null,
  "data": {
    "userId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "张三",
    "username": "2024001",
    "studentId": "2024001",
    "accessToken": "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VySWQiOiJhMWIyYzNkNCJ9...",
    "roleId": 4,
    "classId": 101,
    "schoolId": 1,
    "schoolName": "天择大学",
    "collegeId": 0
   
  }
}
```

**data 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `userId` | String | 用户唯一ID |
| `name` | String | 用户姓名 |
| `username` | String | 用户名/学号 |
| `studentId` | String | 学号 |
| `accessToken` | String | 系统JWT访问令牌，后续请求在 Header 中携带 |
| `roleId` | Integer | 角色ID：1=管理员，3=教师，4=学生 |
| `classId` | Integer | 班级ID |
| `schoolId` | Integer | 学校ID |
| `schoolName` | String | 学校名称 |
| `collegeId` | Integer | 院系ID |
| `majorId` | Integer | 专业ID |

### 错误返回

账号不存在：
```json
{
  "code": 401,
  "msg": "账号不存在",
  "data": null
}
```

密码错误：
```json
{
  "code": 401,
  "msg": "密码错误",
  "data": null
}
```

智云Token无效：
```json
{
  "code": 401,
  "msg": "token 无效！",
  "data": null
}
```

密码解密失败：
```json
{
  "code": 400,
  "msg": "密码错误",
  "data": null
}
```

---

## 3. 生成智云登录Token

输入学号和明文密码，生成一个智云平台格式的 JWT Token，可直接作为登录接口（接口2）的 `TOKEN` 参数使用，方便对接调试。

### 请求说明

| 项目 | 内容 |
|------|------|
| 请求方式 | GET |
| 请求路径 | `/api/user/generateZhiYunToken` |
| 是否需要Token | 否 |

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `username` | String | 是 | 用户名/学号 |
| `password` | String | 是 | 密码（明文） |

### 请求示例

```
GET /server/api/user/generateZhiYunToken?username=2024001&password=123456
```

### 成功返回

```json
{
  "code": 200,
  "msg": "生成成功",
  "data": "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VybmFtZSI6IjIwMjQwMDEiLCJwYXNzd29yZCI6IjEyMzQ1NiJ9..."
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | Integer | 状态码，200 表示成功 |
| `msg` | String | 提示信息 |
| `data` | String | 智云平台格式的 JWT Token（HS256 算法），有效期12小时 |

### 错误返回

```json
{
  "code": 400,
  "msg": "参数错误信息",
  "data": null
}
```

### 使用流程

1. 调用本接口，传入学号和密码，获取智云 Token
2. 调用登录接口（接口2），将获取到的 Token 作为 `TOKEN` 参数传入，完成 SSO 登录

---

## 附录：用户信息表字段说明

数据库表名：`users_info`

| 字段名 | Java属性 | 类型 | 说明 |
|--------|---------|------|------|
| `user_id` | userId | String | 用户ID（主键，UUID） |
| `student_id` | studentId | String | 学号/工号（登录账号，唯一标识） |
| `password` | password | String | 密码 |
| `user_name` | userName | String | 用户姓名 |
| `class_id` | classId | String | 班级ID |
| `class_name` | className | String | 班级名称 |
| `phone` | phone | String | 联系电话 |
| `school_id` | schoolId | String | 学校ID |
| `school_name` | schoolName | String | 学校名称 |
| `role_id` | roleId | Byte | 角色ID：3=教师，4=学生 |
| `zy_user_id` | zyUserId | String | 对应智云平台用户ID |
| `authorize_time` | authorizeTime | Date | 授权开通日期 |
| `authorize_end_time` | authorizeEndTime | Date | 授权结束日期 |
| `create_time` | createTime | Date | 创建时间 |
| `is_deleted` | isDeleted | Boolean | 删除状态：0=未删除，1=已删除 |

---

## 通用说明

### 通用响应结构

所有接口（除同步接口返回纯文本外）统一返回以下 JSON 结构：

```json
{
  "code": 200,
  "msg": "提示信息",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | Integer | HTTP 状态码 |
| `msg` | String | 提示信息，成功时可能为 null |
| `data` | Object | 返回数据，具体结构由各接口定义 |

### 状态码说明

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未认证（Token 无效/过期、账号或密码错误） |
| 403 | 无权限访问 |
| 500 | 服务器内部错误 |

### Token 使用方式

登录成功后，在后续需要认证的接口请求头中携带：

```
Authorization: Bearer {accessToken}
```
