import fs from 'fs/promises';
import path from 'path';
import Link from 'next/link';
import { ChevronRight, ChevronLeft, ListTree, FileCode, Folder, ExternalLink, Download } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSlug from 'rehype-slug';
import GithubSlugger from 'github-slugger';
import DocSidebar, { MarkdownFile } from './DocSidebar';

export const dynamic = 'force-dynamic';

interface TOCItem {
  id: string;
  text: string;
  level: number;
}

async function getMarkdownFiles(dir: string, baseDir: string = dir): Promise<MarkdownFile[]> {
  try {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    const filesPromises = entries.map(async (entry) => {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        return getMarkdownFiles(fullPath, baseDir);
      } else if (entry.name.endsWith('.md')) {
        const relativePath = path.relative(baseDir, fullPath).replace(/\\/g, '/');
        const pathParts = relativePath.split('/');
        const category = pathParts.length > 1 ? pathParts[0] : '01-overview';

        try {
          const content = await fs.readFile(fullPath, 'utf-8');
          const lines = content.split('\n');
          let title = relativePath;

          for (const line of lines) {
            if (line.trim().startsWith('# ')) {
              title = line.replace(/^#\s*/, '').trim();
              break;
            }
          }

          return [{ path: relativePath, title, category, isPdf: false }];
        } catch {
          return [{ path: relativePath, title: relativePath, category, isPdf: false }];
        }
      } else if (entry.name.endsWith('.pdf')) {
        const relativePath = path.relative(baseDir, fullPath).replace(/\\/g, '/');
        const pathParts = relativePath.split('/');
        const category = pathParts.length > 1 ? pathParts[0] : (relativePath.includes('benchmark') || relativePath.includes('agente') ? '02-arquitetura' : '06-arquivo');
        const cleanName = entry.name.replace(/\.pdf$/i, '').replace(/_/g, ' ');
        return [{ path: relativePath, title: cleanName, category, isPdf: true }];
      }
      return [];
    });

    const nestedFiles = await Promise.all(filesPromises);
    const flat = nestedFiles.flat();
    return flat.sort((a, b) => {
      if (a.path.includes('README.md')) return -1;
      if (b.path.includes('README.md')) return 1;
      return a.path.localeCompare(b.path);
    });
  } catch (error) {
    console.error('Error reading directory:', error);
    return [];
  }
}

export default async function TeamPortal({ searchParams }: { searchParams: { doc?: string } }) {
  const resolvedParams = await Promise.resolve(searchParams);
  const currentDoc = resolvedParams?.doc || '';

  const docsDir = path.join(process.cwd(), '../docs');
  const files = await getMarkdownFiles(docsDir);

  let markdownContent = '';
  let docFound = false;

  const defaultFile = files.find(f => f.path.includes('getting-started.md')) || files[0];
  const currentPath = (currentDoc || (defaultFile ? defaultFile.path : '')).replace(/\\/g, '/');
  const isPdf = currentPath.toLowerCase().endsWith('.pdf');

  if (currentPath) {
    try {
      const safePath = path.normalize(currentPath).replace(/^(\.\.(\/|\\|$))+/, '');
      const fullPath = path.join(docsDir, safePath);

      if (fullPath.startsWith(docsDir)) {
        const stat = await fs.stat(fullPath);
        if (stat.isFile()) {
          docFound = true;
          if (!isPdf) {
            markdownContent = await fs.readFile(fullPath, 'utf-8');
          }
        }
      }
    } catch {
      markdownContent = '# Documento não encontrado\nO arquivo selecionado não existe ou não pôde ser carregado.';
    }
  }

  if (!docFound && !isPdf) {
    markdownContent = '# Bem-vindo ao Portal de Documentação\nSelecione um documento na barra lateral para começar a leitura.';
  }

  // Extract Category & Breadcrumb
  const currentFileObj = files.find(f => f.path === currentPath);
  const categoryFolder = currentFileObj ? currentFileObj.category : 'docs';
  const fileBasename = currentPath.split('/').pop() || currentPath;

  // TOC Extraction (only for markdown files)
  const toc: TOCItem[] = [];
  if (!isPdf && markdownContent) {
    const slugger = new GithubSlugger();
    const lines = markdownContent.split('\n');
    let insideCodeBlock = false;

    for (const line of lines) {
      if (line.trim().startsWith('```')) {
        insideCodeBlock = !insideCodeBlock;
        continue;
      }
      if (insideCodeBlock) continue;

      const match = line.match(/^(#{2,3})\s+(.*)/);
      if (match) {
        let text = match[2].trim();
        text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
        const id = slugger.slug(text);
        toc.push({ level: match[1].length, text, id });
      }
    }
  }

  // Pagination Logic
  let currentIndex = files.findIndex(f => f.path === currentPath);
  if (currentIndex === -1) currentIndex = 0;

  const prevDoc = currentIndex > 0 ? files[currentIndex - 1] : null;
  const nextDoc = currentIndex < files.length - 1 ? files[currentIndex + 1] : null;

  return (
    <div className="min-h-screen bg-[#090B10] text-slate-200 selection:bg-sky-500/20 selection:text-sky-200 font-sans">
      {/* Top Institutional Header Bar */}
      <header className="border-b border-slate-800/80 bg-[#0B0E15]">
        <div className="max-w-[96rem] mx-auto px-4 sm:px-6 lg:px-8 py-5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-start sm:items-center gap-4">
            <div className="flex-shrink-0 bg-[#111622] px-3 py-2 rounded-lg border border-slate-800/90 flex items-center justify-center">
              <img
                src="/ciia_logo.png"
                alt="Logo CIIA-DF"
                className="h-10 sm:h-11 w-auto object-contain"
              />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono font-medium tracking-wider text-sky-400 uppercase">
                  CIIA-DF · NIAUnDF
                </span>
                <span className="text-slate-700">•</span>
                <span className="text-[11px] font-mono text-slate-400">
                  Ambiente Experimental
                </span>
              </div>
              <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-slate-50">
                Portal de Orquestração: Benchmark SEI
              </h1>
              <p className="text-xs sm:text-[13px] text-slate-400 max-w-2xl leading-relaxed">
                Documentação técnica, contratos de integração e diretrizes operacionais para avaliação comparativa entre Hermes e LangGraph.
              </p>
            </div>
          </div>

          {/* Institutional Metadata Pills */}
          <div className="flex flex-wrap items-center gap-2 self-start md:self-center">
            <Link
              href="/"
              className="text-[12px] font-mono text-sky-200 bg-sky-950/50 hover:bg-sky-900/60 border border-sky-500/50 px-3 py-1.5 rounded-md transition-colors flex items-center gap-1.5 shadow-sm"
            >
              <span>←</span>
              <span>Landing Page</span>
            </Link>
            <Link
              href="/resultados.html"
              className="text-[12px] font-mono text-slate-300 hover:text-white bg-[#111622] hover:bg-[#182030] border border-slate-700/80 px-3 py-1.5 rounded-md transition-colors"
            >
              Resultados
            </Link>
            <span className="text-[11px] font-mono text-slate-300 bg-[#111622] border border-slate-800 px-2.5 py-1 rounded-md">
              Contratos v0.1
            </span>
          </div>
        </div>
      </header>

      <div className="max-w-[96rem] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Main Documentation Area */}
        <div className="flex flex-col lg:flex-row gap-7 items-start">

          {/* Left Sidebar Navigation */}
          <aside className="w-full lg:w-72 flex-shrink-0 lg:sticky lg:top-6 z-10">
            <DocSidebar files={files} currentPath={currentPath} />
          </aside>

          {/* Main Markdown / PDF Reader Container */}
          <main className="flex-1 min-w-0 bg-[#0C0F17] border border-slate-800/80 rounded-xl flex flex-col overflow-hidden relative w-full">

            {/* Editorial Document Metadata Header (Replaces fake macOS window bar) */}
            <div className="bg-[#080B11] border-b border-slate-800/80 px-6 py-3 flex flex-wrap items-center justify-between gap-3">
              {/* Breadcrumbs Navigation */}
              <div className="flex items-center gap-1.5 text-xs font-mono text-slate-400 overflow-hidden">
                <span className="flex items-center gap-1.5 text-slate-500 flex-shrink-0">
                  <Folder size={13} className="text-slate-500" />
                  docs
                </span>
                <ChevronRight size={12} className="text-slate-600 flex-shrink-0" />
                <span className="text-slate-400 flex-shrink-0">{categoryFolder}</span>
                <ChevronRight size={12} className="text-slate-600 flex-shrink-0" />
                <span className="text-slate-200 font-medium flex items-center gap-1.5 truncate">
                  <FileCode size={13} className="text-sky-400 flex-shrink-0" />
                  {fileBasename}
                </span>
              </div>

              {/* Document Type / Section Indicator */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {!isPdf && toc.length > 0 && (
                  <span className="text-[11px] font-mono text-slate-500 hidden sm:inline">
                    {toc.length} {toc.length === 1 ? 'seção' : 'seções'}
                  </span>
                )}
                {isPdf ? (
                  <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/50 uppercase">
                    Documento PDF
                  </span>
                ) : (
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/60 uppercase">
                    Markdown
                  </span>
                )}
              </div>
            </div>

            {/* Document Body: PDF Viewer or Markdown Reader */}
            {isPdf ? (
              <div className="p-6 lg:p-8 flex flex-col gap-6 flex-1 w-full">
                {/* PDF Control Bar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-[#080B11] border border-slate-800/80 p-4 rounded-lg">
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className="p-2 bg-rose-950/40 border border-rose-800/40 rounded-md text-rose-400 flex-shrink-0">
                      <FileCode size={18} />
                    </div>
                    <div className="flex flex-col overflow-hidden">
                      <div className="flex items-center gap-2">
                        <h2 className="text-sm font-semibold text-slate-100 truncate" title={fileBasename}>
                          {fileBasename}
                        </h2>
                      </div>
                      <span className="text-xs text-slate-400 truncate">
                        Arquivo anexo integrante da documentação do projeto
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <a
                      href={`/api/docs?file=${encodeURIComponent(currentPath)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 bg-slate-800/70 hover:bg-slate-800 border border-slate-700/70 text-slate-200 rounded-md transition-colors"
                    >
                      <ExternalLink size={13} />
                      <span>Abrir em nova aba</span>
                    </a>
                    <a
                      href={`/api/docs?file=${encodeURIComponent(currentPath)}`}
                      download={fileBasename}
                      className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-md transition-colors"
                    >
                      <Download size={13} />
                      <span>Baixar PDF</span>
                    </a>
                  </div>
                </div>

                {/* PDF Embedded Frame */}
                <div className="w-full h-[78vh] min-h-[600px] rounded-lg border border-slate-800/80 bg-[#07090E] overflow-hidden relative flex flex-col">
                  <iframe
                    src={`/api/docs?file=${encodeURIComponent(currentPath)}`}
                    className="w-full h-full border-0 bg-white"
                    title={fileBasename}
                  />
                </div>

                {/* Prev / Next Pagination */}
                <div className="mt-4 pt-6 border-t border-slate-800/80 flex flex-col sm:flex-row gap-3 justify-between items-center">
                  {prevDoc ? (
                    <Link href={`?doc=${encodeURIComponent(prevDoc.path)}`} className="group flex items-center gap-3 bg-[#080B11] border border-slate-800/80 px-4 py-3 rounded-lg hover:border-slate-700 hover:bg-slate-900/60 transition w-full sm:w-1/2">
                      <ChevronLeft size={16} className="text-slate-400 group-hover:text-sky-400 group-hover:-translate-x-0.5 transition-all flex-shrink-0" />
                      <div className="flex flex-col text-left overflow-hidden">
                        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Anterior</span>
                        <span className="text-xs font-medium text-slate-200 truncate group-hover:text-sky-300 transition-colors" title={prevDoc.title}>{prevDoc.title}</span>
                      </div>
                    </Link>
                  ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}

                  {nextDoc ? (
                    <Link href={`?doc=${encodeURIComponent(nextDoc.path)}`} className="group flex items-center justify-end gap-3 bg-[#080B11] border border-slate-800/80 px-4 py-3 rounded-lg hover:border-slate-700 hover:bg-slate-900/60 transition w-full sm:w-1/2 text-right">
                      <div className="flex flex-col overflow-hidden">
                        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Próxima</span>
                        <span className="text-xs font-medium text-slate-200 truncate group-hover:text-sky-300 transition-colors" title={nextDoc.title}>{nextDoc.title}</span>
                      </div>
                      <ChevronRight size={16} className="text-slate-400 group-hover:text-sky-400 group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                    </Link>
                  ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}
                </div>
              </div>
            ) : (
              /* Markdown Render Body */
              <div className="px-6 py-8 sm:px-10 sm:py-10 lg:px-12 lg:py-11 flex-1">
                <div className="prose prose-invert prose-slate max-w-[74ch] text-[15px] leading-[1.75]
                  prose-headings:text-slate-100 prose-headings:font-semibold prose-headings:tracking-tight
                  prose-h1:text-2xl sm:prose-h1:text-[28px] prose-h1:text-slate-50 prose-h1:border-b prose-h1:border-slate-800/80 prose-h1:pb-4 prose-h1:mb-6 prose-h1:leading-snug
                  prose-h2:text-lg sm:prose-h2:text-xl prose-h2:text-slate-100 prose-h2:mt-10 prose-h2:mb-4 prose-h2:pb-2 prose-h2:border-b prose-h2:border-slate-800/50 prose-h2:scroll-mt-8
                  prose-h3:text-base prose-h3:text-slate-200 prose-h3:mt-7 prose-h3:mb-2.5 prose-h3:scroll-mt-8
                  prose-p:text-slate-300 prose-p:leading-[1.75] prose-p:mb-5
                  prose-a:text-sky-400 hover:prose-a:text-sky-300 prose-a:underline prose-a:decoration-sky-500/30 hover:prose-a:decoration-sky-400 prose-a:underline-offset-4 prose-a:transition-colors prose-a:font-medium
                  prose-strong:text-slate-100 prose-strong:font-semibold
                  prose-ul:text-slate-300 prose-ul:mb-5 prose-ol:text-slate-300 prose-ol:mb-5
                  prose-li:marker:text-slate-500 prose-li:my-1
                  prose-code:text-sky-300 prose-code:bg-slate-800/70 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:border prose-code:border-slate-700/60 prose-code:font-mono prose-code:text-[13px] prose-code:font-normal prose-code:before:content-none prose-code:after:content-none
                  prose-pre:bg-[#07090E] prose-pre:border prose-pre:border-slate-800/90 prose-pre:rounded-lg prose-pre:p-4 prose-pre:my-5 prose-pre:shadow-none [&_pre_code]:bg-transparent [&_pre_code]:border-0 [&_pre_code]:p-0 [&_pre_code]:text-slate-200 [&_pre_code]:text-[13px]
                  prose-blockquote:border-l-2 prose-blockquote:border-l-sky-500/70 prose-blockquote:bg-[#0E1420]/70 prose-blockquote:py-2.5 prose-blockquote:px-4 prose-blockquote:rounded-r-lg prose-blockquote:text-slate-300 prose-blockquote:font-normal prose-blockquote:not-italic prose-blockquote:my-5
                  prose-hr:border-slate-800/80 prose-hr:my-8
                ">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSlug]}
                    components={{
                      table: ({ ...props }) => (
                        <div className="overflow-x-auto my-6 border border-slate-800/90 rounded-lg bg-[#080B11]">
                          <table className="w-full text-left border-collapse text-[13.5px] text-slate-300 my-0" {...props} />
                        </div>
                      ),
                      thead: ({ ...props }) => (
                        <thead className="bg-[#0E131F] border-b border-slate-800/90 text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-400" {...props} />
                      ),
                      th: ({ ...props }) => (
                        <th className="px-4 py-2.5 border-r border-slate-800/60 last:border-r-0 font-semibold text-slate-200" {...props} />
                      ),
                      td: ({ ...props }) => (
                        <td className="px-4 py-2.5 border-t border-slate-800/60 border-r border-slate-800/60 last:border-r-0 text-slate-300 leading-relaxed" {...props} />
                      ),
                      tr: ({ ...props }) => (
                        <tr className="hover:bg-slate-800/20 transition-colors" {...props} />
                      ),
                      a: ({ href, children, ...props }) => {
                        if (!href) return <a {...props}>{children}</a>;
                        if (href.startsWith('http') || href.startsWith('mailto:') || href.startsWith('#')) {
                          return (
                            <a
                              href={href}
                              target={href.startsWith('http') ? '_blank' : undefined}
                              rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
                              {...props}
                            >
                              {children}
                            </a>
                          );
                        }
                        let resolvedPath = href;
                        if (!href.startsWith('/')) {
                          const currentDir = path.dirname(currentPath);
                          resolvedPath = path.join(currentDir, href).replace(/\\/g, '/');
                        } else {
                          resolvedPath = href.replace(/^\//, '');
                        }
                        const [docPath, anchor] = resolvedPath.split('#');
                        const hash = anchor ? `#${anchor}` : '';
                        return (
                          <Link href={`?doc=${encodeURIComponent(docPath)}${hash}`} {...props}>
                            {children}
                          </Link>
                        );
                      },
                    }}
                  >
                    {markdownContent}
                  </ReactMarkdown>
                </div>

                {/* Prev / Next Pagination */}
                <div className="mt-14 pt-6 border-t border-slate-800/80 flex flex-col sm:flex-row gap-3 justify-between items-center">
                  {prevDoc ? (
                    <Link href={`?doc=${encodeURIComponent(prevDoc.path)}`} className="group flex items-center gap-3 bg-[#080B11] border border-slate-800/80 px-4 py-3 rounded-lg hover:border-slate-700 hover:bg-slate-900/60 transition w-full sm:w-1/2">
                      <ChevronLeft size={16} className="text-slate-400 group-hover:text-sky-400 group-hover:-translate-x-0.5 transition-all flex-shrink-0" />
                      <div className="flex flex-col text-left overflow-hidden">
                        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Anterior</span>
                        <span className="text-xs font-medium text-slate-200 truncate group-hover:text-sky-300 transition-colors" title={prevDoc.title}>{prevDoc.title}</span>
                      </div>
                    </Link>
                  ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}

                  {nextDoc ? (
                    <Link href={`?doc=${encodeURIComponent(nextDoc.path)}`} className="group flex items-center justify-end gap-3 bg-[#080B11] border border-slate-800/80 px-4 py-3 rounded-lg hover:border-slate-700 hover:bg-slate-900/60 transition w-full sm:w-1/2 text-right">
                      <div className="flex flex-col overflow-hidden">
                        <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Próxima</span>
                        <span className="text-xs font-medium text-slate-200 truncate group-hover:text-sky-300 transition-colors" title={nextDoc.title}>{nextDoc.title}</span>
                      </div>
                      <ChevronRight size={16} className="text-slate-400 group-hover:text-sky-400 group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                    </Link>
                  ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}
                </div>
              </div>
            )}
          </main>

          {/* Right Sidebar / Table of Contents (On this page) */}
          {toc.length > 0 && (
            <aside className="hidden xl:flex w-64 flex-shrink-0 flex-col sticky top-6">
              <div className="pl-4 border-l border-slate-800/80">
                <div className="flex items-center gap-2 mb-3">
                  <ListTree size={14} className="text-slate-400" />
                  <h3 className="text-[11px] font-mono font-semibold tracking-wider text-slate-400 uppercase">
                    Nesta Página
                  </h3>
                </div>
                <nav className="flex flex-col gap-1.5 max-h-[72vh] overflow-y-auto pr-2 custom-scrollbar">
                  {toc.map((item, idx) => (
                    <a
                      key={`${item.id}-${idx}`}
                      href={`#${item.id}`}
                      className={`text-[13px] leading-snug py-1 transition-colors duration-150 ${
                        item.level === 2
                          ? 'text-slate-400 hover:text-slate-100 font-normal'
                          : 'text-slate-500 hover:text-slate-300 pl-3 text-xs'
                      }`}
                    >
                      {item.text}
                    </a>
                  ))}
                </nav>
              </div>
            </aside>
          )}

        </div>
      </div>
    </div>
  );
}
