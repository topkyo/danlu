"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const vm = require("vm");

function loadHelpers() {
  const src = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
  const context = {
    module: { exports: {} },
    exports: {},
    require,
    fs,
    path,
    Date,
    Math,
    Uint8Array,
    DEFAULT_LOCALE: "zh",
    ZH_TEXT: {},
    CURATED_STATUS_LABELS: {},
    ACTION_STATUS_LABELS: {},
    REWRITE_STATUS_LABELS: {},
    REVIEW_REASON_LABELS: {},
  };
  vm.runInNewContext(`${src}\nmodule.exports = { resolvePluginFileSource, sanitizeDropFileName, collectMaterialPathsFromPayload, buildAutoAskQuestion, inferAutoAskFormat, looksLikeUniversalMaterialPayload, splitTextMaterialQuestion };`, context);
  return context.module.exports;
}

describe("Universal Input attachment source handling", () => {
  test("resolvePluginFileSource writes File contents when file.path is missing", async () => {
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "furnace-plugin-vault-"));
    const { resolvePluginFileSource } = loadHelpers();
    const plugin = { repoState: { root: tempRoot }, app: { vault: { adapter: { basePath: tempRoot } } } };
    const file = {
      name: "report:bad/name?.pdf",
      type: "application/pdf",
      arrayBuffer: jest.fn().mockResolvedValue(Buffer.from("%PDF-1.4\n")),
    };

    const source = await resolvePluginFileSource(plugin, file);

    expect(source).toContain(path.join(".aiwiki", "tmp", "product-shell-drop"));
    expect(source).not.toContain("report:bad/name?.pdf");
    expect(path.basename(source)).toMatch(/^report_bad_name_-/);
    expect(path.basename(source)).toMatch(/\.pdf$/);
    expect(fs.readFileSync(source, "utf8")).toBe("%PDF-1.4\n");
    expect(file.arrayBuffer).toHaveBeenCalledTimes(1);
  });

  test("resolvePluginFileSource keeps real absolute paths without copying", async () => {
    const { resolvePluginFileSource } = loadHelpers();
    const absolutePath = path.join(path.sep, "tmp", "paper.pdf");
    const file = { name: "paper.pdf", path: absolutePath, arrayBuffer: jest.fn() };

    await expect(resolvePluginFileSource({}, file)).resolves.toBe(absolutePath);
    expect(file.arrayBuffer).not.toHaveBeenCalled();
  });

  test("source helper persists File objects without file.path before CLI submission", () => {
    const helpersSrc = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
    const inputSrc = fs.readFileSync(path.resolve(__dirname, "../../render_input.js"), "utf8");
    const bundleSrc = fs.readFileSync(path.resolve(__dirname, "../../../main.js"), "utf8");

    expect(helpersSrc).toMatch(/async function resolvePluginFileSource/);
    expect(helpersSrc).toMatch(/typeof file\.arrayBuffer !== "function"/);
    expect(helpersSrc).toMatch(/\.aiwiki"\), "tmp"\), "product-shell-drop"|"\.aiwiki", "tmp", "product-shell-drop"/);
    expect(inputSrc).toMatch(/const source = await resolvePluginFileSource\(plugin, file\)/);
    expect(inputSrc).toMatch(/await plugin\.runDroppedFilesWithAutoAsk\(/);
    expect(inputSrc).not.toMatch(/runUniversalInputCommand\(\{ payload: file\.path \|\| file\.name/);
    expect(bundleSrc).toMatch(/async function resolvePluginFileSource/);
    expect(bundleSrc).toMatch(/async runDroppedFilesWithAutoAsk\(/);
    expect(bundleSrc).toMatch(/await plugin\.runAskCommand\(\{[\s\S]*mode: "run-ask"/);
    expect(bundleSrc).toMatch(/product-shell-drop/);
  });

  test("drop action copy reflects asset-backed PDF and image drops", () => {
    const constantsSrc = fs.readFileSync(path.resolve(__dirname, "../../constants.js"), "utf8");
    const bundleSrc = fs.readFileSync(path.resolve(__dirname, "../../../main.js"), "utf8");

    expect(constantsSrc).toContain("PDF 原件进 raw/assets；Markdown / 仓库快照进 raw/inbox。");
    expect(constantsSrc).toContain("图片原件进 raw/assets。");
    expect(constantsSrc).not.toContain("把 PDF 或仓库快照投进 raw/inbox。");
    expect(constantsSrc).not.toContain("把图片投进 raw/inbox。");
    expect(bundleSrc).toContain("PDF 原件进 raw/assets；Markdown / 仓库快照进 raw/inbox。");
    expect(bundleSrc).toContain("图片原件进 raw/assets。");
  });

  test("collectMaterialPathsFromPayload gathers all supported drop paths", () => {
    const { collectMaterialPathsFromPayload } = loadHelpers();
    const paths = collectMaterialPathsFromPayload({
      note_path: "raw/inbox/note.md",
      asset_path: "raw/assets/a.pdf",
      path: "wiki/sources/source.md",
      original_path: "/home/tim/private/report.pdf",
      report_path: "output/reports/report.md",
      receipt_path: ".aiwiki/state/execution-receipts/r.json",
      result: {
        materials: [
          { state_path: ".aiwiki/state/a.json" },
          { index_path: "wiki/indexes/compile-status.md" },
        ],
      },
      asset_paths: ["raw/assets/a.pdf", "raw/assets/b.pdf"],
    });

    expect(paths).toEqual([
      "raw/inbox/note.md",
      "raw/assets/a.pdf",
      "wiki/sources/source.md",
      "output/reports/report.md",
      ".aiwiki/state/execution-receipts/r.json",
      "raw/assets/b.pdf",
      ".aiwiki/state/a.json",
      "wiki/indexes/compile-status.md",
    ]);
    expect(paths).not.toContain("/home/tim/private/report.pdf");
  });

  test("auto ask drops materials before one note ask unless report is requested", async () => {
    const helpersSrc = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
    const commandSpecsSrc = fs.readFileSync(path.resolve(__dirname, "../../command_specs.js"), "utf8");
    const pendingStateSrc = fs.readFileSync(path.resolve(__dirname, "../../pending_state.js"), "utf8");
    const pendingRuntimeSrc = fs.readFileSync(path.resolve(__dirname, "../../pending_runtime.js"), "utf8");
    const pluginActionsSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin_actions.js"), "utf8");
    const pluginSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin.js"), "utf8");
    const calls = [];
    const context = {
      module: { exports: {} },
      exports: {},
      require,
      Plugin: class {},
    };
    vm.runInNewContext(`${helpersSrc}\n${commandSpecsSrc}\n${pendingStateSrc}\n${pendingRuntimeSrc}\n${pluginActionsSrc}\n${pluginSrc}\nmodule.exports = module.exports;`, context);
    const PluginClass = context.module.exports;
    const plugin = new PluginClass();
    plugin.runUniversalInputCommand = jest
      .fn(async (args) => {
        calls.push(["drop", args]);
        return args.payload.endsWith("b.pdf")
          ? { asset_path: "raw/assets/b.pdf", original_path: "/home/tim/private/b.pdf" }
          : { note_path: "raw/inbox/a.md" };
      });
    plugin.runAskCommand = jest.fn(async (args) => {
      calls.push(["ask", args]);
      return { report_path: "output/reports/r.md" };
    });

    const result = await plugin.runDroppedPayloadsWithAutoAsk({
      payloads: ["a.pdf", "b.pdf"],
      question: "请总结",
      protocol: "research",
    });

    expect(plugin.runUniversalInputCommand).toHaveBeenCalledTimes(2);
    expect(plugin.runUniversalInputCommand).toHaveBeenNthCalledWith(1, { payload: "a.pdf", title: "" });
    expect(plugin.runUniversalInputCommand).toHaveBeenNthCalledWith(2, { payload: "b.pdf", title: "" });
    expect(plugin.runAskCommand).toHaveBeenCalledTimes(1);
    expect(calls.map((item) => item[0])).toEqual(["drop", "drop", "ask"]);
    expect(plugin.runAskCommand).toHaveBeenCalledWith({
      question: expect.stringContaining("材料路径供系统路由使用："),
      format: "report",
      mode: "run-ask",
      protocol: "research",
    });
    const askQuestion = plugin.runAskCommand.mock.calls[0][0].question;
    expect(askQuestion).toContain("raw/inbox/a.md");
    expect(askQuestion).toContain("raw/assets/b.pdf");
    expect(askQuestion).toContain("请总结");
    expect(askQuestion).not.toContain("/home/tim/private/b.pdf");
    expect(result.materialPaths).toEqual(["raw/inbox/a.md", "raw/assets/b.pdf"]);
    expect(result.askFormat).toBe("report");
  });

  test("auto ask passes dropped file names as CLI titles", async () => {
    const helpersSrc = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
    const commandSpecsSrc = fs.readFileSync(path.resolve(__dirname, "../../command_specs.js"), "utf8");
    const pendingStateSrc = fs.readFileSync(path.resolve(__dirname, "../../pending_state.js"), "utf8");
    const pendingRuntimeSrc = fs.readFileSync(path.resolve(__dirname, "../../pending_runtime.js"), "utf8");
    const pluginActionsSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin_actions.js"), "utf8");
    const pluginSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin.js"), "utf8");
    const context = {
      module: { exports: {} },
      exports: {},
      require,
      Plugin: class {},
    };
    vm.runInNewContext(`${helpersSrc}\n${commandSpecsSrc}\n${pendingStateSrc}\n${pendingRuntimeSrc}\n${pluginActionsSrc}\n${pluginSrc}\nmodule.exports = module.exports;`, context);
    const PluginClass = context.module.exports;
    const plugin = new PluginClass();
    plugin.runUniversalInputCommand = jest.fn(async () => ({ note_path: "raw/inbox/trump-visit.md" }));
    plugin.runAskCommand = jest.fn(async () => ({ report_path: "output/reports/r.md" }));

    await plugin.runDroppedFilesWithAutoAsk({
      files: [{ path: "/tmp/1779261245224-7b4c3390-20260513.pdf", name: "特朗普访华预期.pdf" }],
      question: "请总结",
    });

    expect(plugin.runUniversalInputCommand).toHaveBeenCalledWith({
      payload: "/tmp/1779261245224-7b4c3390-20260513.pdf",
      title: "特朗普访华预期.pdf",
    });
  });

  test("auto ask uses report only when the user asks for report-grade output", async () => {
    const helpersSrc = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
    const commandSpecsSrc = fs.readFileSync(path.resolve(__dirname, "../../command_specs.js"), "utf8");
    const pendingStateSrc = fs.readFileSync(path.resolve(__dirname, "../../pending_state.js"), "utf8");
    const pendingRuntimeSrc = fs.readFileSync(path.resolve(__dirname, "../../pending_runtime.js"), "utf8");
    const pluginActionsSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin_actions.js"), "utf8");
    const pluginSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin.js"), "utf8");
    const context = {
      module: { exports: {} },
      exports: {},
      require,
      Plugin: class {},
    };
    vm.runInNewContext(`${helpersSrc}\n${commandSpecsSrc}\n${pendingStateSrc}\n${pendingRuntimeSrc}\n${pluginActionsSrc}\n${pluginSrc}\nmodule.exports = module.exports;`, context);
    const PluginClass = context.module.exports;
    const plugin = new PluginClass();
    plugin.runUniversalInputCommand = jest.fn(async () => ({ note_path: "raw/inbox/a.md" }));
    plugin.runAskCommand = jest.fn(async () => ({ report_path: "output/reports/r.md" }));

    const result = await plugin.runDroppedPayloadsWithAutoAsk({
      payloads: ["a.pdf"],
      question: "请生成一份研究报告，包含证据链和结论",
    });

    expect(plugin.runAskCommand).toHaveBeenCalledWith(expect.objectContaining({
      format: "report",
      mode: "run-ask",
    }));
    expect(result.askFormat).toBe("report");
  });

  test("auto ask always uses report mode", () => {
    const { inferAutoAskFormat } = loadHelpers();

    expect(inferAutoAskFormat("引用报告：output/reports/foo.md\n那好吧，你的llm是什么模型？", [])).toBe("report");
    expect(inferAutoAskFormat("引用报告：output/reports/foo.md 那好吧，你的llm是什么模型？", [])).toBe("report");
    expect(inferAutoAskFormat("引用报告：output/reports/foo.md\n请生成一份研究报告，包含证据链", [])).toBe("report");
  });

  test("built main routes report auto ask through background submit", () => {
    const bundleSrc = fs.readFileSync(path.resolve(__dirname, "../../../main.js"), "utf8");

    expect(bundleSrc).toMatch(/function buildAskCommandSpec/);
    expect(bundleSrc).toMatch(/const longRunning = mode === "run-ask" && finalFormat === "report"/);
    expect(bundleSrc).toMatch(/const command = longRunning \? "run-ask-submit" : mode/);
    expect(bundleSrc).toMatch(/backgroundSubmit: longRunning/);
  });

  test("buildAutoAskQuestion includes material paths and user question", () => {
    const { buildAutoAskQuestion } = loadHelpers();
    const question = buildAutoAskQuestion("请总结要点", ["raw/inbox/a.md", "raw/assets/b.pdf"]);

    expect(question).toMatch(/^请总结要点/);
    expect(question).toContain("材料路径供系统路由使用：raw/inbox/a.md、raw/assets/b.pdf");
    expect(question).toContain("请总结要点");
  });

  test("drop modals resolve selected files instead of falling back to bare names", () => {
    const modalsSrc = fs.readFileSync(path.resolve(__dirname, "../../modals.js"), "utf8");
    const bundleSrc = fs.readFileSync(path.resolve(__dirname, "../../../main.js"), "utf8");

    expect(modalsSrc).toMatch(/await resolvePluginFileSource\(self\.plugin, file\)/);
    expect(modalsSrc).toMatch(/setInitialTitle\(value\)/);
    expect(modalsSrc).toMatch(/titleInput\.value = this\.initialTitle/);
    expect(modalsSrc).toMatch(/titleInput\.value = String\(file\.name \|\| ""\)\.trim\(\)/);
    expect(modalsSrc).not.toMatch(/file\.path \|\| file\.name/);
    expect(bundleSrc).toMatch(/await resolvePluginFileSource\(self\.plugin, file\)/);
    expect(bundleSrc).toMatch(/titleInput\.value = String\(file\.name \|\| ""\)\.trim\(\)/);
  });

  test("splitTextMaterialQuestion detects material plus question", () => {
    const { looksLikeUniversalMaterialPayload, splitTextMaterialQuestion } = loadHelpers();

    expect(splitTextMaterialQuestion("https://example.com/report 重新分析下"))
      .toEqual({ payload: "https://example.com/report", question: "重新分析下" });
    expect(splitTextMaterialQuestion("https://example.com/report\n重新分析下\n给出结论"))
      .toEqual({ payload: "https://example.com/report", question: "重新分析下\n给出结论" });
    expect(splitTextMaterialQuestion("引用报告：output/reports/r.md\n重新分析下"))
      .toBeNull();
    expect(looksLikeUniversalMaterialPayload("引用报告：output/reports/r.md"))
      .toBe(false);
    expect(splitTextMaterialQuestion("重新分析下"))
      .toBeNull();
  });
});
