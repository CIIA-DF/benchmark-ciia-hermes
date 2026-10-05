import fs from 'fs/promises';
import path from 'path';
import Link from 'next/link';
import { Users, GitBranch, Terminal, ShieldAlert, FileText, ChevronRight, ChevronLeft, BookOpen, ListTree } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeSlug from 'rehype-slug';
import GithubSlugger from 'github-slugger';

export const dynamic = 'force-dynamic';

interface MarkdownFile {
  path: string;
  title: string;
}

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

          return [{ path: relativePath, title }];
        } catch {
          return [{ path: relativePath, title: relativePath }];
        }
      }
      return [];
    });

    const nestedFiles = await Promise.all(filesPromises);
    const flat = nestedFiles.flat();
    return flat.sort((a, b) => {
      if (a.path === 'README.md') return -1;
      if (b.path === 'README.md') return 1;
      return a.path.localeCompare(b.path);
    });
  } catch (error) {
    console.error('Error reading directory:', error);
    return [];
  }
}

export default async function TeamPortal({ searchParams }: { searchParams: { doc?: string } }) {
  // Handling Next 14 and Next 15 differences dynamically
  const resolvedParams = await Promise.resolve(searchParams);
  const currentDoc = resolvedParams?.doc || '';

  const docsDir = path.join(process.cwd(), '../docs');
  const files = await getMarkdownFiles(docsDir);

  let markdownContent = '';
  let docFound = false;

  const currentPath = currentDoc || (files.find(f => f.path === 'README.md')?.path || '');

  if (currentPath) {
    try {
      const safePath = path.normalize(currentPath).replace(/^(\.\.(\/|\\|$))+/, '');
      const fullPath = path.join(docsDir, safePath);

      if (fullPath.startsWith(docsDir)) {
        markdownContent = await fs.readFile(fullPath, 'utf-8');
        docFound = true;
      }
    } catch (error) {
      markdownContent = '# Documento não encontrado\nO arquivo selecionado não existe ou não pôde ser carregado.';
    }
  }

  if (!docFound) {
    markdownContent = '# Bem-vindo ao Developer Hub\nSelecione um documento na barra lateral para começar.';
  }

  // --- TOC Extraction ---
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
      text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1'); // clean links
      const id = slugger.slug(text);
      toc.push({ level: match[1].length, text, id });
    }
  }

  // --- Pagination Logic ---
  let currentIndex = files.findIndex(f => f.path === currentPath);
  if (currentIndex === -1) currentIndex = 0;

  const prevDoc = currentIndex > 0 ? files[currentIndex - 1] : null;
  const nextDoc = currentIndex < files.length - 1 ? files[currentIndex + 1] : null;

  return (
    <div className="min-h-screen bg-[#061224] text-white selection:bg-cyan-500/30 font-sans">
      <div className="max-w-[90rem] mx-auto px-4 sm:px-6 lg:px-8 py-12 flex flex-col gap-10">

        {/* Hero Section */}
        <header className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-cyan-400 via-blue-500 to-indigo-500 bg-clip-text text-transparent">
              Portal de Orquestração: Projeto SEI
            </h1>
            <p className="text-xl text-slate-400 max-w-3xl leading-relaxed">
              Painel de roteamento e diretrizes para os 15 membros da equipe de P&D.
            </p>
          </div>
        </header>

        {/* Documentation Area */}
        <div className="flex flex-col lg:flex-row gap-8 items-start">

          {/* Left Sidebar / File Explorer */}
          <aside className="w-full lg:w-72 flex-shrink-0 flex flex-col gap-6 lg:sticky lg:top-8 z-10">
            <div className="bg-white/5 border border-white/10 rounded-2xl p-5 backdrop-blur-md shadow-2xl">
              <div className="flex items-center gap-3 mb-5 pb-3 border-b border-white/10">
                <BookOpen className="text-cyan-400" size={20} />
                <h2 className="text-base font-semibold tracking-wide text-slate-200">Menu Principal</h2>
              </div>

              <nav className="flex flex-col gap-1 max-h-[65vh] overflow-y-auto pr-2 custom-scrollbar">
                {files.map((file) => {
                  const isActive = currentPath === file.path;
                  return (
                    <Link
                      key={file.path}
                      href={`?doc=${encodeURIComponent(file.path)}`}
                      className={`flex items-center justify-between p-2.5 rounded-xl transition-all duration-200 group ${isActive
                        ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 shadow-[inset_0_0_15px_rgba(6,182,212,0.05)]'
                        : 'text-slate-400 border border-transparent hover:bg-white/5 hover:text-slate-200'
                        }`}
                    >
                      <div className="flex items-center gap-3 overflow-hidden">
                        <FileText size={16} className={`flex-shrink-0 ${isActive ? 'opacity-100 text-cyan-400' : 'opacity-50 group-hover:opacity-100'}`} />
                        <span className="truncate text-sm font-medium" title={file.title}>{file.title}</span>
                      </div>
                      {isActive && (
                        <ChevronRight size={16} className="text-cyan-400 flex-shrink-0" />
                      )}
                    </Link>
                  );
                })}
              </nav>
            </div>

            {/* Terminal Mockup Card */}
            <div className="bg-[#030816] border border-slate-800/80 rounded-2xl overflow-hidden font-mono text-sm shadow-2xl relative group">
              <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
              <div className="bg-[#050B1A] border-b border-slate-800/80 px-4 py-3 flex items-center justify-between">
                <div className="flex gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
                </div>
                <span className="text-slate-500 text-xs font-medium tracking-wider uppercase">CLI Utils</span>
              </div>
              <div className="p-5 text-slate-300 flex flex-col gap-3 relative z-10 leading-relaxed">
                <div className="flex flex-col">
                  <p className="flex items-center gap-2 text-cyan-300"><Terminal size={14} className="opacity-70" /> <span>uv sync --locked</span></p>
                  <p className="text-slate-500/80 pl-6 text-[11px]"># Instalação controlada</p>
                </div>
                <div className="flex flex-col">
                  <p className="flex items-center gap-2 text-cyan-300"><Terminal size={14} className="opacity-70" /> <span>make demo</span></p>
                  <p className="text-slate-500/80 pl-6 text-[11px]"># Simulação experimental</p>
                </div>
              </div>
            </div>
          </aside>

          {/* Main Content Area */}
          <main className="flex-1 min-w-0 bg-[#09152C] border border-white/5 rounded-3xl p-8 lg:p-12 shadow-2xl flex flex-col relative">
            <div className="prose prose-invert prose-slate max-w-none 
              prose-headings:text-slate-100 prose-headings:font-bold prose-headings:tracking-tight
              prose-h1:text-3xl prose-h1:text-cyan-50 prose-h1:border-b prose-h1:border-white/10 prose-h1:pb-4 prose-h1:mb-8
              prose-h2:text-2xl prose-h2:mt-12 prose-h2:mb-6 prose-h2:scroll-mt-8
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
              prose-th:text-slate-200 prose-th:bg-white/5 prose-th:p-3
              prose-td:border-t prose-td:border-white/10 prose-td:p-3
            ">
              <ReactMarkdown rehypePlugins={[rehypeSlug]}>{markdownContent}</ReactMarkdown>
            </div>

            {/* Pagination / Prev & Next */}
            <div className="mt-16 pt-8 border-t border-white/10 flex flex-col sm:flex-row gap-4 justify-between items-center">
              {prevDoc ? (
                <Link href={`?doc=${encodeURIComponent(prevDoc.path)}`} className="group flex items-center gap-4 bg-white/5 border border-white/5 p-4 rounded-2xl hover:bg-white/10 transition w-full sm:w-1/2">
                  <div className="p-2 bg-white/5 rounded-full group-hover:-translate-x-1 transition-transform">
                    <ChevronLeft size={20} className="text-cyan-400" />
                  </div>
                  <div className="flex flex-col text-left overflow-hidden">
                    <span className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">Anterior</span>
                    <span className="text-sm font-medium text-slate-300 truncate group-hover:text-cyan-300 transition-colors" title={prevDoc.title}>{prevDoc.title}</span>
                  </div>
                </Link>
              ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}

              {nextDoc ? (
                <Link href={`?doc=${encodeURIComponent(nextDoc.path)}`} className="group flex items-center justify-end gap-4 bg-white/5 border border-white/5 p-4 rounded-2xl hover:bg-white/10 transition w-full sm:w-1/2 text-right">
                  <div className="flex flex-col overflow-hidden">
                    <span className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">Próxima</span>
                    <span className="text-sm font-medium text-slate-300 truncate group-hover:text-cyan-300 transition-colors" title={nextDoc.title}>{nextDoc.title}</span>
                  </div>
                  <div className="p-2 bg-white/5 rounded-full group-hover:translate-x-1 transition-transform">
                    <ChevronRight size={20} className="text-cyan-400" />
                  </div>
                </Link>
              ) : <div className="hidden sm:block w-full sm:w-1/2"></div>}
            </div>
          </main>

          {/* Right Sidebar / Table of Contents */}
          {toc.length > 0 && (
            <aside className="hidden xl:flex w-56 flex-shrink-0 flex-col gap-4 sticky top-8">
              <div className="flex items-center gap-2 mb-2 pb-2 border-b border-white/5">
                <ListTree size={16} className="text-cyan-400" />
                <h3 className="text-xs font-bold tracking-widest text-slate-400 uppercase">Nesta Página</h3>
              </div>
              <nav className="flex flex-col gap-2.5 border-l-2 border-white/5 pl-4 py-1">
                {toc.map((item, idx) => (
                  <a
                    key={`${item.id}-${idx}`}
                    href={`#${item.id}`}
                    className={`text-sm leading-tight transition-colors duration-200 ${item.level === 2
                        ? 'text-slate-300 hover:text-cyan-400 font-medium'
                        : 'text-slate-500 hover:text-cyan-300 ml-4 text-[13px]'
                      }`}
                  >
                    {item.text}
                  </a>
                ))}
              </nav>
            </aside>
          )}

        </div>
      </div>
    </div>
  );
}
