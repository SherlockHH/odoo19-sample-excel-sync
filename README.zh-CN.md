# Sample Excel Export & Update — Odoo 19

[English](README.md) | 简体中文

独立 Odoo 19 add-on：样品单导出 Excel，工厂修改后预览差异并回填原样品行。Odoo 是最终数据来源。

**状态：候选版本。** 自动测试使用合成样品模块验证 Odoo 19 框架行为，不代表公司原有自定义模块、Excel/WPS 或正式环境已验收。请先在隔离测试环境安装。

## 使用

1. 打开样品单，点击 **Export Sample Excel**，选择全部样品行或当前单内的一家工厂。
2. 将文件发给工厂，仅编辑四个业务字段：Color & Finish、Other Sample Requirements、Sample Ready Date、Factory Feedback。
3. **由原导出人**打开同一样品单，点击 **Import Sample Updates** 上传返回文件。
4. 点击 **Preview Changes**。未变化字段隐藏；普通更新默认使用 Excel，清空默认忽略；真正冲突必须选择使用 Excel 或保留 Odoo。
5. **Confirm Update** 保存，样品单现有消息区记录成功修改。再次导出会包含已保存值。

完成日期仅接受正式 Excel 日期或 `YYYY-MM-DD` 文本。TBC、月底完成等说明写在 Factory Feedback。数量和产品识别列仅展示；删除行不会删除 Odoo 记录，不接受新增样品行。

不包含客户信息、规格、认证；表头只包含样品单号。每条样品行占一行。现有 Plug/Logo 放在独立只读参考列，防止把显示附注反复写进可编辑 remarks。系列要求需要先在 Odoo 对应样品行中明确维护，本模块不会从旧 Excel 的位置猜测其适用范围。现有备注图 `x_remark_image` 尚不导出，含重要要求的图片请先明确成文字；产品缩略图不能替代样品要求。

版式沿用原业务模板的浅青色表头、Calibri 加粗字体、黑色细边框、白底数据区和较大产品图；不使用蓝色可编辑区域或隔行底色，不自动复制旧表里的人工绿色标记。

## Excel 排序与限制

- 使用完整 Excel 表格的筛选/排序功能；隐藏 Record Key 列属于同一张表。不要只排序部分列、改列名或删除隐藏标识页。
- 产品图片设置为随单元格移动和缩放；Excel/WPS 的实际排序行为仍需人工验收。导入不依赖图片识别产品。
- 不完整型号、数量不阻止按有效行标识回填。改动识别列会提示重新导出。
- 最多 2000 行、文件最大 8 MB、解压最大 48 MB、文本单元格最多 8000 字符。
- 不接受宏、嵌入对象、外部链接、公式或错误单元格。导出的 `=...` 等原始备注被保存为纯文本。
- 导出快照有效期 90 天；预览有效期 24 小时。系统定期清理过期内部元数据，没有批次管理页面。
- 工厂不需要 Odoo 账号；返回文件由原导出人回填。Excel 文件本身包含样品业务信息，应按公司流程分发。

## 安装（交给 IT）

本模块包含 Python 代码，需由 IT 部署到 Odoo 服务的 addons 路径。GitHub 下载并不自动安装，网页的 ZIP 导入功能也不一定支持 Python add-on。

1. 确认 **Odoo 19**，已安装公司提供的 `sample_management_mlx`、`project` 和 `mail`。
2. 先在测试环境备份数据库与 filestore，并停用外发邮件、短信、Webhook 等真实外部发送。
3. 在 **Odoo 服务实际使用的 Python 环境**安装根目录 `requirements.txt` 中的库；不要随意替换整个 Odoo 的依赖集合。先验证版本兼容。
4. 将仓库中的 **`sample_excel_sync/`** 目录复制到自定义 addons 路径（或使用发布的专用模块 ZIP，先解压）。
5. 重启 Odoo 服务、更新应用列表，安装 **Sample Excel Export & Update**。
6. 验收通过后，对正式环境备份并由 IT 部署同一提交。后续代码更新使用 `-u sample_excel_sync`。

**绝不要部署 `ci/fixtures/sample_management_mlx`。它是自动测试用的合成替身，不是公司的业务模块。**

仓库目录结构：

```text
sample_excel_sync/   可安装模块（含 Odoo 集成测试）
tests/              不需要 Odoo 的核心测试
ci/fixtures/        仅 CI 的合成样品模块
ci/Dockerfile       官方 Odoo 19 测试镜像
tools/package.py    仅打包可安装模块
docs/               设计、测试和部署说明
```

## 兼容契约

复用 `mlx.sample.request` 和 `mlx.sample.request.line`，不新建业务字段、不创建或删除样品行。

| Excel 可编辑列 | 现有字段 |
|---|---|
| Color & Finish | `sample_color` |
| Other Sample Requirements | `remarks` |
| Sample Ready Date | `factory_ready_date` |
| Factory Feedback | `factory_comment` |

请求需有 `company_id`、`state`、`name`、`line_ids`，行需有 `request_id`、`supplier_id`、`product_tmpl_id`、`quantity`、`state`。基础表单按唯一名称 `mlx.sample.request.form` 继承；若 IT 已更名或存在多个同名主表单，请在测试环境修正继承目标。

取消的样品行仍导出并标识，但禁止修改；已取消或已解决的请求需先在原业务流程中重新打开。

### 精确任务联动

支持现有 `project.task.sample_request_line_id` 或旧版 `x_sample_line_id`。重复、冲突或跨公司的链接会阻止操作，不能用任务描述文字模糊匹配。仅当样品完成日期发生变化时，同步已有对应任务的 `sample_ready_date` / `x_sample_ready_date`，不新增任务、不主动改状态或安排活动。

为兼容已知旧模块，导入写入期间使用服务器内部 ContextVar，精确跳过以下两个会进行全量项目同步/状态跟进的旧服务器动作：

- `sample_request_project_link.action_auto_sample_line_lifecycle`
- `sample_request_project_link.action_auto_sample_task_stage_followup`

并使用已有项目联动递归保护 context。保护范围只在本模块的确认写入调用栈内，不关闭自动化、不改其配置，也不跳过其他动作。没有这些 XML ID 的安装环境保持正常调用。未知 Python overrides/自动化仍可能存在，**IT 必须用真实自定义模块验证其副作用**。发现状态变化会使该次导入回滚。

## 权限、冲突与数据保护

只给内部用户提供两个 transient wizard；业务字段读取及写入始终使用当前用户的 ORM 权限、记录规则、字段权限及所选公司。唯一额外的关联核对是用 sudo 比较精确关联任务的数量，遇到当前用户看不到的任务直接拒绝操作，不返回其 ID 或内容。

隐藏列只携带不可猜测的行标识。真实行 ID、导出范围、原值和预览计划保存在 Odoo 内部私有快照中。普通用户不能创建、查看或修改快照；服务只在创建/查询自身内部元数据时使用 sudo。快照绑定导出人、请求及公司。

确认前锁定预览、请求、相关行及已有任务，重新校验文件哈希、当前值、产品/工厂/请求身份、状态、任务链接与权限。更新用服务器计划生成，不信任预览显示列。预览一次性消费；相同文件重新预览后，已保存的内容自然成为无变化。

所有写入和消息记录完成后，再核对当前样品单的行身份、数量、状态、四个业务字段及精确关联任务的日期、状态、负责人和项目；发现超出本次允许修改范围的变化则回滚。

并发边界：旧版 `x_sample_line_id` 是整数关联，其他模块在独立事务中新建/重绑任务时不一定锁定样品行。本模块不对所有项目任务的创建/改绑增加全局钩子，因此不能宣称关联变更已完全串行化。IT 需要在测试环境验证此场景，并在导入期间避免同时重绑关联任务。

事务失败会撤销本次更新。回退旧代码**不会撤销已导入的数据**，需要根据消息记录人工恢复，或由 IT 按已验证的数据库/filestore恢复方案处理。

## 开发与自动检查

Windows：在仓库根目录建立 `.venv`，安装 `requirements-dev.txt`，双击 `运行程序.bat` 运行核心测试。它不是 Odoo 服务启动器。

```shell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m bandit -r sample_excel_sync -ll
.venv\Scripts\python -m pip_audit -r requirements.txt
.venv\Scripts\python tools/package.py
```

GitHub Actions 会运行上述检查，并在官方 Odoo 19 + PostgreSQL 中安装模块、运行合成契约集成测试。仅使用本地合成数据和临时数据库，不连接生产 Odoo，不需要任何生产凭据。

安全扫描没有发现问题不等于没有漏洞；扫描工具、依赖数据库及测试覆盖范围均有边界。详见 [验收清单](docs/acceptance.md)。

## 公开仓库边界

仅包含原创模块代码、说明和合成测试资料。不得提交真实样品 Excel、客户资料、账号、API Key、生产数据库配置、数据库/filestore备份、原业务模块源码或本地环境目录。测试中出现的数据库密码仅用于销毁即弃的 CI PostgreSQL 服务。

License: LGPL-3.0-or-later. 第三方库和既有 Odoo/业务模块保留其各自许可。
