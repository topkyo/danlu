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
  vm.runInNewContext(`${src}\nmodule.exports = { resolvePluginFileSource, sanitizeDropFileName, collectMaterialPathsFromPayload, buildAutoAskQuestion, splitTextMaterialQuestion };`, context);
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
    expect(bundleSrc).toMatch(/await this\.runAskCommand\(\{[\s\S]*mode: "run-ask"/);
    expect(bundleSrc).toMatch(/product-shell-drop/);
  });

  test("collectMaterialPathsFromPayload gathers all supported drop paths", () => {
    const { collectMaterialPathsFromPayload } = loadHelpers();
    const paths = collectMaterialPathsFromPayload({
      note_path: "raw/inbox/note.md",
      asset_path: "raw/assets/a.pdf",
      path: "wiki/sources/source.md",
      original_path: "/home/tim/private/report.pdf",
      report_path: "output/reports/report.md",
      receipt_path: "output/control/execution-receipts/r.json",
      result: {
        materials: [
          { state_path: ".aiwiki/state/a.json" },
          { index_path: "wiki/indexes/log.md" },
        ],
      },
      asset_paths: ["raw/assets/a.pdf", "raw/assets/b.pdf"],
    });

    expect(paths).toEqual([
      "raw/inbox/note.md",
      "raw/assets/a.pdf",
      "wiki/sources/source.md",
      "output/reports/report.md",
      "output/control/execution-receipts/r.json",
      "raw/assets/b.pdf",
      ".aiwiki/state/a.json",
      "wiki/indexes/log.md",
    ]);
    expect(paths).not.toContain("/home/tim/private/report.pdf");
  });

  test("auto ask drops materials before one report ask without leaking question title", async () => {
    const helpersSrc = fs.readFileSync(path.resolve(__dirname, "../../helpers.js"), "utf8");
    const pluginSrc = fs.readFileSync(path.resolve(__dirname, "../../plugin.js"), "utf8");
    const calls = [];
    const context = {
      module: { exports: {} },
      exports: {},
      require,
      Plugin: class {},
    };
    vm.runInNewContext(`${helpersSrc}\n${pluginSrc}\nmodule.exports = module.exports;`, context);
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
    expect(plugin.runUniversalInputCommand).toHaveBeenNthCalledWith(1, { payload: "a.pdf" });
    expect(plugin.runUniversalInputCommand).toHaveBeenNthCalledWith(2, { payload: "b.pdf" });
    expect(plugin.runAskCommand).toHaveBeenCalledTimes(1);
    expect(calls.map((item) => item[0])).toEqual(["drop", "drop", "ask"]);
    expect(plugin.runAskCommand).toHaveBeenCalledWith({
      question: expect.stringContaining("本次投喂材料路径："),
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
  });

  test("buildAutoAskQuestion includes material paths and user question", () => {
    const { buildAutoAskQuestion } = loadHelpers();
    const question = buildAutoAskQuestion("请总结要点", ["raw/inbox/a.md", "raw/assets/b.pdf"]);

    expect(question).toContain("本次投喂材料路径：");
    expect(question).toContain("- raw/inbox/a.md");
    expect(question).toContain("- raw/assets/b.pdf");
    expect(question).toContain("用户问题：");
    expect(question).toContain("请总结要点");
  });

  test("drop modals resolve selected files instead of falling back to bare names", () => {
    const modalsSrc = fs.readFileSync(path.resolve(__dirname, "../../modals.js"), "utf8");
    const bundleSrc = fs.readFileSync(path.resolve(__dirname, "../../../main.js"), "utf8");

    expect(modalsSrc).toMatch(/await resolvePluginFileSource\(self\.plugin, file\)/);
    expect(modalsSrc).not.toMatch(/file\.path \|\| file\.name/);
    expect(bundleSrc).toMatch(/await resolvePluginFileSource\(self\.plugin, file\)/);
  });

  test("splitTextMaterialQuestion detects material plus question", () => {
    const { splitTextMaterialQuestion } = loadHelpers();

    expect(splitTextMaterialQuestion("https://example.com/report 重新分析下"))
      .toEqual({ payload: "https://example.com/report", question: "重新分析下" });
    expect(splitTextMaterialQuestion("https://example.com/report\n重新分析下\n给出结论"))
      .toEqual({ payload: "https://example.com/report", question: "重新分析下\n给出结论" });
    expect(splitTextMaterialQuestion("重新分析下"))
      .toBeNull();
  });
});
