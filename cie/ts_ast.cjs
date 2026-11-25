// Parse TypeScript with the compiler API. Only supplied files and relative local imports are resolved.
"use strict";
const fs = require("fs");
const path = require("path");
const ts = require(process.argv[3]);

const root = path.resolve(process.argv[2]);
const files = JSON.parse(fs.readFileSync(0, "utf8")).map(f => path.resolve(root, f));
const allowed = new Set(files);
const rel = f => path.relative(root, f).split(path.sep).join("/");
const options = { noEmit: true, noLib: true, allowJs: false, jsx: ts.JsxEmit.Preserve,
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext };
const host = ts.createCompilerHost(options);
const originalGetSourceFile = host.getSourceFile.bind(host);
host.getSourceFile = (fileName, ...args) => allowed.has(path.resolve(fileName)) ?
  originalGetSourceFile(fileName, ...args) : undefined;
const configFile = path.join(root, "tsconfig.json");
let configOptions = {};
if (fs.existsSync(configFile)) {
  const parsed = ts.parseConfigFileTextToJson(configFile, fs.readFileSync(configFile, "utf8"));
  if (!parsed.error) configOptions = parsed.config.compilerOptions || {};
}
const baseUrl = path.resolve(root, configOptions.baseUrl || ".");
const aliases = configOptions.paths || {};
function resolveLocal(base) {
  const withoutJs = base.replace(/\.(js|jsx|mjs|cjs)$/, "");
  for (const prefix of [base, withoutJs]) {
    for (const [suffix, extension] of [["", ts.Extension.Ts], [".ts", ts.Extension.Ts],
                                       [".tsx", ts.Extension.Tsx], ["/index.ts", ts.Extension.Ts],
                                       ["/index.tsx", ts.Extension.Tsx]]) {
      const candidate = prefix + suffix;
      if (allowed.has(candidate)) return { resolvedFileName: candidate, extension };
    }
  }
  return undefined;
}
host.resolveModuleNames = (names, containingFile) => names.map(name => {
  if (name.startsWith(".")) return resolveLocal(path.resolve(path.dirname(containingFile), name));
  for (const [pattern, destinations] of Object.entries(aliases)) {
    const wildcard = pattern.indexOf("*");
    if (wildcard < 0 ? name !== pattern :
        !(name.startsWith(pattern.slice(0, wildcard)) && name.endsWith(pattern.slice(wildcard + 1)))) continue;
    const matched = wildcard < 0 ? "" : name.slice(wildcard, name.length - (pattern.length - wildcard - 1));
    for (const destination of destinations) {
      const mapped = destination.replace("*", matched);
      const resolved = resolveLocal(path.resolve(baseUrl, mapped));
      if (resolved) return resolved;
    }
  }
  return undefined;
});
const program = ts.createProgram(files, options, host);
const checker = program.getTypeChecker();
const result = {};
const symbolToId = new Map();
const bodies = [];

function position(source, offset) {
  const at = source.getLineAndCharacterOfPosition(offset);
  return { line: at.line + 1, column: at.character + 1 };
}
function declarationName(node) {
  if (ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node)) return node.name;
  if (ts.isVariableDeclaration(node)) return node.name;
  return undefined;
}
function executable(node) {
  if ((ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node)) && node.body) return node.body;
  if (ts.isVariableDeclaration(node) && node.initializer &&
      (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) return node.initializer.body;
  return undefined;
}
for (const file of files) {
  const source = program.getSourceFile(file);
  const key = rel(file);
  const stat = fs.statSync(file);
  result[key] = { symbols: [], calls: [], diagnostics: "", clang_exit: 0, source_size: stat.size };
  if (!source) {
    result[key].diagnostics = "TypeScript could not parse this file";
    result[key].clang_exit = 1;
    continue;
  }
  const diagnostics = source.parseDiagnostics.map(d => ts.flattenDiagnosticMessageText(d.messageText, " "));
  if (diagnostics.length) {
    result[key].diagnostics = diagnostics.join("; ");
    result[key].clang_exit = 1;
  }
  function visit(node, scope) {
    let nextScope = scope;
    if (ts.isClassDeclaration(node) || ts.isModuleDeclaration(node)) {
      if (node.name) nextScope = [...scope, node.name.getText(source)];
    }
    const body = executable(node);
    const nameNode = declarationName(node);
    if (body && nameNode && ts.isIdentifier(nameNode)) {
      const name = nameNode.text;
      const qualified = [...scope, name].join(".");
      const id = `fn:typescript:${key}:${qualified}`;
      const start = position(source, node.getStart(source));
      const end = position(source, node.getEnd());
      const at = position(source, nameNode.getStart(source));
      result[key].symbols.push({ id, name, qualified_name: qualified, language: "typescript",
        file: key, line: at.line, column: at.column, start_line: start.line, end_line: end.line,
        module: key.replace(/\.(ts|tsx)$/, ""), type: "function", linkage: "module" });
      const symbol = checker.getSymbolAtLocation(nameNode);
      if (symbol) symbolToId.set(symbol, id);
      bodies.push({ source, key, id, body });
      nextScope = [...scope, name];
    }
    ts.forEachChild(node, child => visit(child, nextScope));
  }
  visit(source, []);
}
for (const {source, key, id, body} of bodies) {
  function visit(node) {
    if (node !== body && (ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) ||
        ts.isArrowFunction(node) || ts.isMethodDeclaration(node))) return;
    if (ts.isCallExpression(node)) {
      const callee = ts.isPropertyAccessExpression(node.expression) ? node.expression.name : node.expression;
      let symbol = checker.getSymbolAtLocation(callee);
      if (symbol && (symbol.flags & ts.SymbolFlags.Alias)) {
        try { symbol = checker.getAliasedSymbol(symbol); } catch (_) { symbol = undefined; }
      }
      const target = symbolToId.get(symbol) || null;
      const at = position(source, node.expression.getStart(source));
      result[key].calls.push({ source: id, target, target_name: node.expression.getText(source),
        file: key, line: at.line, column: at.column, type: "calls" });
    }
    ts.forEachChild(node, visit);
  }
  visit(body);
}
process.stdout.write(JSON.stringify(result));
