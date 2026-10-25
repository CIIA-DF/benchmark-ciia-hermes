'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Search, FileText, ChevronRight, ChevronDown, X, Menu, FileSpreadsheet } from 'lucide-react';

export interface MarkdownFile {
  path: string;
  title: string;
  category: string;
  isPdf?: boolean;
}

interface DocSidebarProps {
  files: MarkdownFile[];
  currentPath: string;
}

const CATEGORY_NAMES: Record<string, string> = {
  '00-comece-aqui': '00. Comece Aqui',
  '01-overview': '01. Visão Geral',
  '02-arquitetura': '02. Arquitetura',
  '03-equipes': '03. Equipes',
  '04-operacoes': '04. Operações',
  '05-decisoes': '05. Decisões',
  '06-arquivo': '06. Arquivo Histórico',
  'outros': 'Outros Documentos',
};

export default function DocSidebar({ files, currentPath }: DocSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const activeFileObj = files.find(f => f.path === currentPath);
  const initialCategory = activeFileObj ? activeFileObj.category : '01-overview';

  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({
    [initialCategory]: true,
    '00-comece-aqui': true,
    '01-overview': true,
    '02-arquitetura': true,
    '03-equipes': true,
    '04-operacoes': true,
    '05-decisoes': true,
    '06-arquivo': true,
  });

  const toggleCategory = (cat: string) => {
    setOpenCategories(prev => ({
      ...prev,
      [cat]: !prev[cat]
    }));
  };

  const filteredFiles = files.filter(file => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return file.title.toLowerCase().includes(query) || file.path.toLowerCase().includes(query);
  });

  const categoriesMap: Record<string, MarkdownFile[]> = {};
  filteredFiles.forEach(file => {
    const cat = file.category || 'outros';
    if (!categoriesMap[cat]) {
      categoriesMap[cat] = [];
    }
    categoriesMap[cat].push(file);
  });

  const categoryKeys = Object.keys(CATEGORY_NAMES).filter(key => categoriesMap[key] && categoriesMap[key].length > 0);

  return (
    <>
      {/* Mobile Menu Trigger */}
      <button
        onClick={() => setIsMobileMenuOpen(true)}
        className="lg:hidden flex items-center justify-between bg-[#0C0F17] border border-slate-800/90 rounded-lg px-4 py-3 w-full text-slate-200 mb-2 text-xs font-medium tracking-wide hover:bg-slate-900 transition-colors"
      >
        <span className="flex items-center gap-2.5">
          <Menu size={16} className="text-sky-400" />
          <span>Índice da Documentação</span>
        </span>
        <span className="font-mono text-[11px] text-slate-400 bg-slate-800/70 px-2 py-0.5 rounded">
          {files.length} docs
        </span>
      </button>

      {/* Mobile Backdrop */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-xs lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar Container */}
      <div className={`
        fixed top-0 left-0 bottom-0 z-50 w-[85%] max-w-xs bg-[#090B10] border-r border-slate-800/90 shadow-2xl transition-transform duration-200 ease-out
        lg:static lg:w-auto lg:max-w-none lg:bg-[#0C0F17] lg:border lg:border-slate-800/80 lg:rounded-xl lg:p-4 lg:shadow-none lg:translate-x-0 lg:flex lg:flex-col lg:gap-4
        ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="flex flex-col h-full lg:h-auto p-5 lg:p-0 gap-4">
          <Link href="/chat" className="rounded-lg border border-teal-800 bg-teal-950/40 px-4 py-3 text-sm text-teal-200 hover:bg-teal-900/40">Abrir chat experimental ↗</Link>

          {/* Mobile Close Button */}
          <button
            onClick={() => setIsMobileMenuOpen(false)}
            className="lg:hidden absolute top-4 right-4 p-1.5 bg-slate-900 border border-slate-800 rounded-md text-slate-400 hover:text-white transition-colors"
          >
            <X size={16} />
          </button>

          {/* Sidebar Header */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
            <h2 className="text-[11px] font-mono font-semibold tracking-wider text-slate-400 uppercase">
              Repositório de Docs
            </h2>
            <span className="hidden lg:inline-block text-[11px] font-mono bg-slate-800/70 text-slate-300 border border-slate-700/60 px-2 py-0.5 rounded">
              {files.length} arq.
            </span>
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filtrar por título ou caminho..."
              className="w-full bg-[#07090E] border border-slate-800/90 rounded-lg pl-8 pr-8 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/60 focus:ring-1 focus:ring-sky-500/20 transition-all"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-200 p-0.5"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Categories Tree */}
          <nav className="flex flex-col gap-3 flex-1 overflow-y-auto pr-1 custom-scrollbar max-h-[calc(100vh-14rem)]">
            {categoryKeys.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center font-mono">
                Nenhum documento correspondente.
              </p>
            ) : (
              categoryKeys.map(catKey => {
                const catTitle = CATEGORY_NAMES[catKey] || catKey;
                const catFiles = categoriesMap[catKey] || [];
                const isOpen = searchQuery.trim() !== '' || !!openCategories[catKey];

                return (
                  <div key={catKey} className="flex flex-col gap-1">
                    <button
                      onClick={() => toggleCategory(catKey)}
                      className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-slate-800/40 text-slate-300 hover:text-white transition-colors text-xs font-semibold tracking-tight group text-left"
                    >
                      <span className="truncate">{catTitle}</span>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span className="text-[10px] font-mono text-slate-500">
                          {catFiles.length}
                        </span>
                        {isOpen ? (
                          <ChevronDown size={13} className="text-slate-500 group-hover:text-slate-300" />
                        ) : (
                          <ChevronRight size={13} className="text-slate-600 group-hover:text-slate-400" />
                        )}
                      </div>
                    </button>

                    {isOpen && (
                      <div className="flex flex-col gap-0.5 pl-2.5 ml-2 border-l border-slate-800/80">
                        {catFiles.map(file => {
                          const isActive = currentPath === file.path;
                          return (
                            <Link
                              key={file.path}
                              href={`?doc=${encodeURIComponent(file.path)}`}
                              onClick={() => setIsMobileMenuOpen(false)}
                              className={`flex items-start justify-between py-1.5 px-2.5 rounded-r-md text-[13px] transition-colors group ${
                                isActive
                                  ? 'bg-sky-500/[0.09] text-slate-50 font-medium border-l-2 border-sky-400 -ml-[11px] pl-[19px]'
                                  : 'text-slate-400 hover:bg-slate-800/30 hover:text-slate-200 font-normal'
                              }`}
                            >
                              <div className="flex items-start gap-2 min-w-0 pr-1">
                                {file.isPdf ? (
                                  <FileSpreadsheet size={14} className={`mt-0.5 flex-shrink-0 ${isActive ? 'text-rose-400' : 'text-slate-500 group-hover:text-slate-400'}`} />
                                ) : (
                                  <FileText size={14} className={`mt-0.5 flex-shrink-0 ${isActive ? 'text-sky-400' : 'text-slate-500 group-hover:text-slate-400'}`} />
                                )}
                                <span className="leading-snug truncate" title={file.title}>
                                  {file.title}
                                </span>
                              </div>
                              {file.isPdf && (
                                <span className="text-[9px] font-mono font-semibold px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/50 uppercase flex-shrink-0 mt-0.5">
                                  PDF
                                </span>
                              )}
                            </Link>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </nav>
        </div>
      </div>
    </>
  );
}
