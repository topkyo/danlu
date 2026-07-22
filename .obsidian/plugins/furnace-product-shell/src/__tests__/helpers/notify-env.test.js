"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function loadHelpersNotifyContext() {
  const context = {
    console,
    require,
    Array,
    String,
    Number,
    Object,
    Set,
    Date,
    RegExp,
  };
  const source = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
  vm.runInNewContext(source, context, { filename: "helpers.js" });
  return context;
}

test("buildNotifyEnv enables feishu from non-empty webhook URL", () => {
  const { buildNotifyEnv } = loadHelpersNotifyContext();
  expect(
    buildNotifyEnv({
      feishuWebhookUrl: "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
      wecomWebhookUrl: "",
    })
  ).toEqual({
    AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL: "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
    AIWIKI_NOTIFY_ENABLED_CHANNELS: "feishu",
  });
});

test("buildNotifyEnv enables both channels from non-empty webhook URLs", () => {
  const { buildNotifyEnv } = loadHelpersNotifyContext();
  expect(
    buildNotifyEnv({
      feishuWebhookUrl: "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
      wecomWebhookUrl: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xyz",
    })
  ).toEqual({
    AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL: "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
    AIWIKI_NOTIFY_WECOM_WEBHOOK_URL: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xyz",
    AIWIKI_NOTIFY_ENABLED_CHANNELS: "feishu,wecom",
  });
});

test("buildNotifyEnv emits nothing when webhook URLs are empty", () => {
  const { buildNotifyEnv } = loadHelpersNotifyContext();
  expect(buildNotifyEnv({})).toEqual({});
  expect(
    buildNotifyEnv({
      feishuWebhookUrl: "  ",
      wecomWebhookUrl: "",
      enabledChannels: ["feishu", "wecom"],
    })
  ).toEqual({});
});
