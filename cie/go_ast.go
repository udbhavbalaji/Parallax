// Command go_ast extracts conservative call facts using only Go's standard parser.
// It compiles this trusted helper, never code from the analyzed repository.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type input struct {
	Root   string   `json:"root"`
	Files  []string `json:"files"`
	Module string   `json:"module"`
}
type symbol struct {
	ID            string `json:"id"`
	Name          string `json:"name"`
	QualifiedName string `json:"qualified_name"`
	Language      string `json:"language"`
	File          string `json:"file"`
	Line          int    `json:"line"`
	Column        int    `json:"column"`
	StartLine     int    `json:"start_line"`
	EndLine       int    `json:"end_line"`
	Module        string `json:"module"`
	Type          string `json:"type"`
	Linkage       string `json:"linkage"`
}
type call struct {
	Source     string `json:"source"`
	Target     string `json:"target"`
	TargetName string `json:"target_name"`
	File       string `json:"file"`
	Line       int    `json:"line"`
	Column     int    `json:"column"`
	Type       string `json:"type"`
}
type facts struct {
	Symbols     []symbol `json:"symbols"`
	Calls       []call   `json:"calls"`
	Diagnostics string   `json:"diagnostics"`
	ClangExit   int      `json:"clang_exit"`
	SourceSize  int64    `json:"source_size"`
}
type parsed struct {
	path    string
	file    *ast.File
	imports map[string]string
}
type definition struct {
	key          string
	path         string
	fn           *ast.FuncDecl
	receiverName string
	receiverType string
	id           string
	packageName  string
}

func receiver(expr ast.Expr) string {
	switch x := expr.(type) {
	case *ast.StarExpr:
		return receiver(x.X)
	case *ast.Ident:
		return x.Name
	case *ast.IndexExpr:
		return receiver(x.X)
	case *ast.IndexListExpr:
		return receiver(x.X)
	}
	return ""
}
func main() {
	var in input
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil {
		panic(err)
	}
	fset := token.NewFileSet()
	output := map[string]*facts{}
	files := []parsed{}
	names := map[string]string{}
	packageByDir := map[string]string{}
	ambiguousDir := map[string]bool{}
	defs := []definition{}
	for _, relative := range in.Files {
		absolute := filepath.Join(in.Root, filepath.FromSlash(relative))
		data, err := os.ReadFile(absolute)
		if err != nil {
			panic(err)
		}
		record := &facts{Symbols: []symbol{}, Calls: []call{}, SourceSize: int64(len(data))}
		output[relative] = record
		file, err := parser.ParseFile(fset, absolute, data, parser.AllErrors)
		if err != nil {
			record.Diagnostics = err.Error()
			record.ClangExit = 1
		}
		if file == nil {
			continue
		}
		imports := map[string]string{}
		for _, item := range file.Imports {
			imported, parseErr := strconv.Unquote(item.Path.Value)
			if parseErr != nil {
				continue
			}
			alias := filepath.Base(imported)
			if item.Name != nil {
				alias = item.Name.Name
			}
			imports[alias] = imported
		}
		files = append(files, parsed{relative, file, imports})
		directory := filepath.ToSlash(filepath.Dir(relative))
		if directory == "" {
			directory = "."
		}
		packageName := file.Name.Name
		if !strings.HasSuffix(relative, "_test.go") {
			if existing, seen := packageByDir[directory]; seen && existing != packageName {
				ambiguousDir[directory] = true
			} else {
				packageByDir[directory] = packageName
			}
		}
		for _, declaration := range file.Decls {
			fn, ok := declaration.(*ast.FuncDecl)
			if !ok || fn.Body == nil {
				continue
			}
			recvType, recvName := "", ""
			if fn.Recv != nil && len(fn.Recv.List) > 0 {
				recvType = receiver(fn.Recv.List[0].Type)
				if len(fn.Recv.List[0].Names) > 0 {
					recvName = fn.Recv.List[0].Names[0].Name
				}
			}
			qualified := fn.Name.Name
			if recvType != "" {
				qualified = recvType + "." + qualified
			}
			id := "fn:go:" + directory + ":" + packageName + ":" + qualified
			key := directory + ":" + packageName + ":" + qualified
			names[key] = id
			at := fset.Position(fn.Name.Pos())
			start := fset.Position(fn.Pos())
			end := fset.Position(fn.End())
			record.Symbols = append(record.Symbols, symbol{id, fn.Name.Name, qualified, "go", relative,
				at.Line, at.Column, start.Line, end.Line, directory, "function", "package"})
			defs = append(defs, definition{key, relative, fn, recvName, recvType, id, packageName})
		}
	}
	parsedFiles := map[string]parsed{}
	for _, file := range files {
		parsedFiles[file.path] = file
	}
	for _, def := range defs {
		file := parsedFiles[def.path]
		directory := filepath.ToSlash(filepath.Dir(def.path))
		if directory == "" {
			directory = "."
		}
		ast.Inspect(def.fn.Body, func(node ast.Node) bool {
			if _, nested := node.(*ast.FuncLit); nested {
				return false
			}
			expression, ok := node.(*ast.CallExpr)
			if !ok {
				return true
			}
			target, targetName := "", ""
			switch fun := expression.Fun.(type) {
			case *ast.Ident:
				targetName = fun.Name
				if fun.Obj == nil || fun.Obj.Kind == ast.Fun {
					target = names[directory+":"+def.packageName+":"+fun.Name]
				}
			case *ast.SelectorExpr:
				targetName = fun.Sel.Name
				if x, ok := fun.X.(*ast.Ident); ok {
					targetName = x.Name + "." + fun.Sel.Name
					if x.Name == def.receiverName && def.receiverType != "" {
						target = names[directory+":"+def.packageName+":"+def.receiverType+"."+fun.Sel.Name]
					} else if importPath, imported := file.imports[x.Name]; imported && in.Module != "" &&
						(x.Obj == nil || x.Obj.Kind == ast.Pkg) {
						importedDir := ""
						if importPath == in.Module {
							importedDir = "."
						}
						if strings.HasPrefix(importPath, in.Module+"/") {
							importedDir = strings.TrimPrefix(importPath, in.Module+"/")
						}
						if importedDir != "" && !ambiguousDir[importedDir] {
							target = names[importedDir+":"+packageByDir[importedDir]+":"+fun.Sel.Name]
						}
					}
				}
			}
			at := fset.Position(expression.Fun.Pos())
			output[def.path].Calls = append(output[def.path].Calls, call{def.id, target, targetName,
				def.path, at.Line, at.Column, "calls"})
			return true
		})
	}
	if err := json.NewEncoder(os.Stdout).Encode(output); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
