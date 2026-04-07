# 审阅规则

- decision 页面默认从 `proposed` 开始，并沿显式审阅状态推进。
- judgment 页面默认从 `tentative` 开始，并始终保留明确的 confidence。
- 用 review workflow 把 decision 和 judgment 页面从队列里推进出去。
- review note 应记录状态为什么变化、接下来要看什么。
- 进入 approved、rejected、superseded 或 revisit 等状态时，必须带 `reviewed_at`。
