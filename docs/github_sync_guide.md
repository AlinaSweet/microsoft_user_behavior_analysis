# GitHub Desktop 上传与日常同步说明

本地项目目录：`/Users/alina/Desktop/实习/Github`。
远程仓库：[打开 GitHub 项目](https://github.com/AlinaSweet/microsoft_user_behavior_analysis)。
当前远程仓库名：`microsoft_user_behavior_analysis`，2026-10-24核对为公开。下述首次发布记录保留当时名称与私有可见性。

## 首次上传的操作

1. 打开 GitHub Desktop，选择 File → Add Local Repository。
2. 输入本地项目目录，点击 Add Repository。这是接入已经存在的 Git 仓库。
3. 选择 main 分支，点击 Publish repository。
4. 仓库名称填写 microsoft-store-user-behavior-analysis，保留 Keep this code private，发布到个人账户。
5. 点击 Publish Repository，等待完成。Repository → View on GitHub 可以打开网页检查。
6. 切换到 dev，点击 Publish branch，使日常开发分支也存在于远程。

main 保存稳定版本，dev 用来日常开发。feature/<任务名称> 从 dev 创建，用于单项任务；任务完成后合并回 dev。

## 每次工作的同步步骤

1. 在 Current Repository 选择本项目，在 Current Branch 选择 dev。
2. 开始工作前点击 Fetch origin。如果随后出现 Pull origin，点击它取回远程改动。
3. 修改和保存本地项目文件后，在 Changes 查看本次变化并勾选需要提交的文件。
4. 在 Summary 填写本次改动说明。例如 docs: 补充数据字段说明，或 feat: 新增数据读取功能。
5. 点击 Commit to dev。这一步把改动保存到本地 Git 历史。
6. 点击 Push origin。这一步把已提交的改动上传到 GitHub。
7. 如需检查网页，打开 Repository → View on GitHub，并在网页分支选择器选择 dev。

Fetch 是检查远程更新，Pull 是下载更新，Commit 是保存本地版本，Push 是上传已提交版本。保存文件后仍需 Commit 和 Push 才会出现在远程。

建议每完成一个可以描述清楚的小任务就提交并上传；每天结束工作前再次确认已推送。若没有新提交，无需重复推送。

## 将稳定成果更新到 main

1. 确认 dev 的改动已经提交和推送。
2. 切换到 main，先 Fetch/Pull 获取远程更新。
3. 在 Branch → Merge into current branch 中选择 dev，完成合并。
4. 点击 Push origin，将稳定成果更新到 main。
5. 回到 dev 继续后续开发。

多人合作或出现合并冲突时，先确认变更内容，再处理冲突后提交和推送。

## 哪些内容会上传

代码、README、配置、依赖清单、文档和受 Git 跟踪的报告会上传。
原始 CSV、本机虚拟环境、大型中间数据及被 .gitignore 排除的结果文件保存在本地。
当前 data/raw/user_behavior.csv 是指向本机原始 CSV 的符号链接，该链接没有进入版本记录。
小型 CSV 汇总现在可以提交；大型数据的清单登记和共享规则见 [数据管理说明](data_management.md)。新增文件暂存后、提交和推送前，可运行 bash scripts/run_project.sh check-git 检查大小和目录规则。

## 官方说明

- [添加本地仓库](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop)
- [发布已有项目](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop?platform=mac)
- [提交和推送改动](https://docs.github.com/en/desktop/making-changes-in-a-branch/committing-and-reviewing-changes-to-your-project-in-github-desktop)


## 编码规范生效后的日常同步

1. 从 dev 建立 feature/任务名，修改文件后运行 `bash scripts/check_quality.sh --format`。
2. 在 GitHub Desktop 查看 Changes；写 `feat:`、`fix:`、`refactor:` 或 `docs:` 开头的提交说明，然后 Commit。
3. 点击 Push origin；首次新分支显示 Publish branch。项目 hooks 会先执行检查；失败时根据 .cache/quality/ 日志修复。
4. 在 GitHub 的 Actions 查看 Quality 通过，再评审改动并合入 dev；里程碑确认后更新 main。
5. 合入后在 GitHub Desktop 切换 dev/main 并 Fetch/Pull，开始下一次任务前再次 Fetch。

检查规则和本地 hooks 可以被人为绕过，所以不能代替服务端分支保护。目前未配置服务端保护，不应把未通过检查的代码合入主干。检查通过记录只对相同代码、配置和工具版本有效。
