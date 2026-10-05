import fs from 'fs/promises';
import path from 'path';
import Link from 'next/link';
import { ChevronRight, ChevronLeft, ListTree, FileCode, Folder } from 'lucide-react';
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
        const relativePath = path.relative(baseDir, fullPath);
        const pathParts = relativePath.split(path.sep);
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

          return [{ path: relativePath, title, category }];
        } catch {
          return [{ path: relativePath, title: relativePath, category }];
        }
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
  const currentPath = currentDoc || (defaultFile ? defaultFile.path : '');

  if (currentPath) {
    try {
      const safePath = path.normalize(currentPath).replace(/^(\.\.(\/|\\|$))+/, '');
      const fullPath = path.join(docsDir, safePath);

      if (fullPath.startsWith(docsDir)) {
        markdownContent = await fs.readFile(fullPath, 'utf-8');
        docFound = true;
      }
    } catch {
      markdownContent = '# Documento não encontrado\nO arquivo selecionado não existe ou não pôde ser carregado.';
    }
  }

  if (!docFound) {
    markdownContent = '# Bem-vindo ao Portal de Documentação\nSelecione um documento na barra lateral para começar a leitura.';
  }

  // Extract Category & Breadcrumb
  const currentFileObj = files.find(f => f.path === currentPath);
  const categoryFolder = currentFileObj ? currentFileObj.category : 'docs';
  const fileBasename = currentPath.split(path.sep).pop() || currentPath;

  // TOC Extraction
  const toc: TOCItem[] = [];
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

  // Pagination Logic
  let currentIndex = files.findIndex(f => f.path === currentPath);
  if (currentIndex === -1) currentIndex = 0;

  const prevDoc = currentIndex > 0 ? files[currentIndex - 1] : null;
  const nextDoc = currentIndex < files.length - 1 ? files[currentIndex + 1] : null;

  return (
    <div className="min-h-screen bg-[#061224] text-white selection:bg-cyan-500/30 font-sans">
      <div className="max-w-[92rem] mx-auto px-4 sm:px-6 lg:px-8 py-10 flex flex-col gap-8">

        {/* Header Section */}
        <header className="flex flex-col gap-3 pb-6 border-b border-white/10">
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono font-semibold tracking-widest text-cyan-400 uppercase bg-cyan-500/10 border border-cyan-500/20 px-3 py-1 rounded-full">
              Centro de Pesquisa P&D
            </span>
          </div>
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-400 bg-clip-text text-transparent">
            Portal de Orquestração: Experimento SEI
          </h1>
          <p className="text-sm md:text-base text-slate-400 max-w-3xl leading-relaxed">
            Documentação técnica, diretrizes de desenvolvimento e guias de infraestrutura para os 15 pesquisadores e desenvolvedores.
          </p>
        </header>

        {/* Main Documentation Area */}
        <div className="flex flex-col lg:flex-row gap-8 items-start">

          {/* Left Sidebar (MkDocs Navigation) */}
          <aside className="w-full lg:w-80 flex-shrink-0 lg:sticky lg:top-8 z-10">
            <DocSidebar files={files} currentPath={currentPath} />
          </aside>

          {/* Main Markdown Reader Container */}
          <main className="flex-1 min-w-0 bg-[#09152C] border border-white/10 rounded-2xl shadow-2xl flex flex-col overflow-hidden relative">

            {/* Mac-Style Window Top Header */}
            <div className="bg-[#040B18] border-b border-white/10 px-6 py-3.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-[#FF5F56]"></div>
                <div className="w-3 h-3 rounded-full bg-[#FFBD2E]"></div>
                <div className="w-3 h-3 rounded-full bg-[#27C93F]"></div>
              </div>

              {/* Breadcrumbs Navigation */}
              <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                <span className="flex items-center gap-1 text-slate-500">
                  <Folder size={13} className="text-cyan-400/70" />
                  docs
                </span>
                <ChevronRight size={12} className="text-slate-600" />
                <span className="text-slate-400 font-medium">{categoryFolder}</span>
                <ChevronRight size={12} className="text-slate-600" />
                <span className="text-cyan-300 font-semibold flex items-center gap-1">
                  <FileCode size={13} className="text-cyan-400" />
                  {fileBasename}
                </span>
              </div>
            </div>

            {/* Markdown Render Body */}
            <div className="p-8 lg:p-12 flex-1">
              <div className="prose prose-invert prose-slate max-w-none 
                prose-headings:text-slate-100 prose-headings:font-bold prose-headings:tracking-tight
                prose-h1:text-3xl prose-h1:text-cyan-50 prose-h1:border-b prose-h1:border-white/10 prose-h1:pb-4 prose-h1:mb-8
                prose-h2:text-2xl prose-h2:mt-10 prose-h2:mb-5 prose-h2:scroll-mt-8
                prose-h3:text-xl prose-h3:mt-8 prose-h3:scroll-mt-8
                prose-p:text-slate-300 prose-p:leading-relaxed prose-p:mb-6
                prose-a:text-cyan-400 hover:prose-a:text-cyan-300 prose-a:no-underline prose-a:transition-colors prose-a:font-medium
                prose-strong:text-slate-200
                prose-ul:text-slate-300 prose-ul:mb-6 prose-ol:text-slate-300 prose-ol:mb-6
                prose-li:marker:text-cyan-500/50
                prose-code:text-cyan-200 prose-code:bg-[#030816] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:border prose-code:border-white/10 prose-code:font-mono prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                prose-pre:bg-[#030816] prose-pre:border prose-pre:border-white/10 prose-pre:shadow-xl prose-pre:mb-6
                prose-blockquote:border-l-cyan-500 prose-blockquote:bg-cyan-950/10 prose-blockquote:py-2 prose-blockquote:px-5 prose-blockquote:rounded-r-xl prose-blockquote:text-slate-300 prose-blockquote:font-normal prose-blockquote:not-italic prose-blockquote:mb-6
                prose-hr:border-white/10 prose-hr:my-8
              ">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeSlug]}
                  components={{
                    table: ({ ...props }) => (
                      <div className="overflow-x-auto my-6 border border-white/10 rounded-xl bg-[#030816]">
                        <table className="w-full text-left border-collapse text-sm text-slate-300" {...props} />
                      </div>
                    ),
                    thead: ({ ...props }) => (
                      <thead className="bg-white/5 border-b border-white/10 text-xs font-semibold uppercase tracking-wider text-slate-200" {...props} />
                    ),
                    th: ({ ...props }) => (
                      <th className="p-3.5 border-r border-white/5 last:border-r-0 font-semibold text-cyan-300" {...props} />
                    ),
                    td: ({ ...props }) => (
                      <td className="p-3.5 border-t border-white/5 border-r border-white/5 last:border-r-0 text-slate-300 leading-normal" {...props} />
                    ),
                    tr: ({ ...props }) => (
                      <tr className="hover:bg-white/[0.02] transition-colors" {...props} />
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
                        resolvedPath = path.join(currentDir, href);
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
              <div className="mt-16 pt-8 border-t border-white/10 flex flex-col sm:flex-row gap-4 justify-between items-center">
                {prevDoc ? (
                  <Link href={`?doc=${encodeURIComponent(prevDoc.path)}`} className="group flex items-center gap-4 bg-white/5 border border-white/10 p-4 rounded-xl hover:bg-white/10 hover:border-cyan-500/30 transition w-full sm:w-1/2">
                    <div className="p-2 bg-white/5 rounded-lg group-hover:-translate-x-1 transition-transform">
                      <ChevronLeft size={18} className="text-cyan-400" />
                    </div>
                    <div className="flex flex-col text-left overflow-hidden">
                      <span className="text-[11px] text-slate-500 uppercase font-bold tracking-wider mb-0.5">Anterior</span>
                      <span className="text-xs font-medium text-slate-300 truncate group-hover:text-cyan-300 transition-colors" title={prevDoc.title}>{prevDoc.title}</span>
                    </div>
                  </Link>
                ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}

                {nextDoc ? (
                  <Link href={`?doc=${encodeURIComponent(nextDoc.path)}`} className="group flex items-center justify-end gap-4 bg-white/5 border border-white/10 p-4 rounded-xl hover:bg-white/10 hover:border-cyan-500/30 transition w-full sm:w-1/2 text-right">
                    <div className="flex flex-col overflow-hidden">
                      <span className="text-[11px] text-slate-500 uppercase font-bold tracking-wider mb-0.5">Próxima</span>
                      <span className="text-xs font-medium text-slate-300 truncate group-hover:text-cyan-300 transition-colors" title={nextDoc.title}>{nextDoc.title}</span>
                    </div>
                    <div className="p-2 bg-white/5 rounded-lg group-hover:translate-x-1 transition-transform">
                      <ChevronRight size={18} className="text-cyan-400" />
                    </div>
                  </Link>
                ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}
              </div>
            </div>
          </main>

          {/* Right Sidebar / Table of Contents (On this page) */}
          {toc.length > 0 && (
            <aside className="hidden xl:flex w-60 flex-shrink-0 flex-col gap-4 sticky top-8">
              <div className="bg-white/5 border border-white/10 rounded-2xl p-4 backdrop-blur-md shadow-xl">
                <div className="flex items-center gap-2 mb-3 pb-2.5 border-b border-white/10">
                  <ListTree size={16} className="text-cyan-400" />
                  <h3 className="text-xs font-bold tracking-wider text-slate-300 uppercase">Nesta Página</h3>
                </div>
                <nav className="flex flex-col gap-2 max-h-[70vh] overflow-y-auto pr-1 custom-scrollbar">
                  {toc.map((item, idx) => (
                    <a
                      key={`${item.id}-${idx}`}
                      href={`#${item.id}`}
                      className={`text-xs leading-relaxed transition-colors duration-200 ${
                        item.level === 2
                          ? 'text-slate-300 hover:text-cyan-400 font-medium'
                          : 'text-slate-500 hover:text-cyan-300 pl-3 border-l border-white/10 text-[11px]'
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
