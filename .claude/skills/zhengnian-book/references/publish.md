# 发布流程（书稿 → 网页 → 线上）

书稿目录：`book-慢即是快/`。网页项目：`BusinessWeb/`（git 仓库，远端 main 推送后由 GitHub Pages 与 Vercel 自动部署）。

## 步骤

1. **复制正文**：把 `book-慢即是快/*.md` 复制到 `BusinessWeb/public/first-book/`（网页镜像整个书稿目录里的 md；脚本、csv、pdf、html 不复制）。
2. **改页面清单**：章节新增、改名、换文件名时，修改 `BusinessWeb/src/pages/FirstBook.tsx` 的 `PARTS`：`no`、`title`、`file`、`status`。
3. **检查**：`cd BusinessWeb && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -c FirstBook`（应为0；项目里其他文件有历史遗留的类型报错，与本书无关）；`npm run build` 应输出 `built in`。
4. **只提交书稿相关文件**：
   `git add src/pages/FirstBook.tsx public/first-book`
   `git commit -m "..."`（提交信息写清改了哪几章）
   `git push origin main`
   不要 `git add -A`：工作区有用户自己的未提交改动（热力图组件、server/market.mjs、changelog.json、App.tsx 的 MyBooks 路由等）。
5. **核对线上**：用 curl 请求线上的 md 文件，确认新内容已生效：
   - `https://business-web-black.vercel.app/first-book/<URL编码的文件名>`
   - `https://turbosnails.github.io/BusinessWeb/first-book/<URL编码的文件名>`
   GitHub Actions 的运行记录需要 `gh auth login`，没登录就只能靠上面的请求核对。

## 注意

- 提交信息结尾要带系统给出的署名行。
- 推送前先 `git fetch`，看 main 有没有被别人（另一轮修订）推进；有的话先拉取，别用 force。
- 新数字先登记 `附件-数据/数字核对表.md`，再发布。
