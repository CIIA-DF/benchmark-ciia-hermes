'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { BookOpen, Search, Folder, FolderOpen, FileText, ChevronRight, ChevronDown, X, Menu } from 'lucide-react';

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
  '01-overview': '01. Visão Geral',
  '02-arquitetura': '02. Arquitetura',
  '03-equipes': '03. Equipes',
  '04-operacoes': '04. Operações',
  '05-decisoes': '05. Decisões',
  'outros': 'Outros Documentos',
};

export default function DocSidebar({ files, currentPath }: DocSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  
  // Find which category the active file belongs to so it starts expanded
  const activeFileObj = files.find(f => f.path === currentPath);
  const initialCategory = activeFileObj ? activeFileObj.category : '01-overview';
  
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({
    [initialCategory]: true,
    '01-overview': true,
    '02-arquitetura': true,
    '03-equipes': true,
    '04-operacoes': true,
    '05-decisoes': true,
  });

  const toggleCategory = (cat: string) => {
    setOpenCategories(prev => ({
      ...prev,
      [cat]: !prev[cat]
    }));
  };

  // Filter files by search query
  const filteredFiles = files.filter(file => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return file.title.toLowerCase().includes(query) || file.path.toLowerCase().includes(query);
  });

  // Group files by category
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
      {/* Botão de Menu Sanduíche (Visível apenas no Mobile) */}
      <button 
        onClick={() => setIsMobileMenuOpen(true)}
        className="lg:hidden flex items-center justify-center gap-3 bg-white/5 border border-white/10 rounded-xl px-5 py-4 w-full text-slate-100 mb-2 font-bold tracking-wider shadow-lg hover:bg-white/10 transition-colors"
      >
        <Menu size={22} className="text-cyan-400" />
        <span className="text-sm uppercase">Navegação do Menu</span>
      </button>

      {/* Overlay Escuro para Mobile */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 z-40 bg-[#020617]/80 backdrop-blur-sm lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Container do Sidebar (Menu Lateral) */}
      <div className={`
        fixed top-0 left-0 bottom-0 z-50 w-[85%] max-w-sm bg-[#061224] border-r border-white/10 shadow-[20px_0_40px_rgba(0,0,0,0.5)] transition-transform duration-300 ease-in-out
        lg:static lg:w-auto lg:max-w-none lg:bg-white/5 lg:border lg:rounded-2xl lg:p-5 lg:backdrop-blur-md lg:shadow-2xl lg:translate-x-0 lg:flex lg:flex-col lg:gap-5
        ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="flex flex-col h-full lg:h-auto p-6 lg:p-0">
          
          {/* Botão de Fechar no Mobile */}
          <button 
            onClick={() => setIsMobileMenuOpen(false)}
            className="lg:hidden absolute top-5 right-5 p-2 bg-white/5 border border-white/10 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X size={20} />
          </button>

          {/* Sidebar Header */}
          <div className="flex items-center justify-between pb-4 border-b border-white/10 mb-5 lg:mb-0">
            <div className="flex items-center gap-2.5">
              <img src="/ciia_logo.png" alt="Logo CIIA" className="h-6 w-auto object-contain" />
              <h2 className="text-base font-bold tracking-wider text-slate-200 uppercase">Documentação</h2>
            </div>
            <span className="hidden lg:inline-block text-sm font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 px-2.5 py-0.5 rounded-full font-medium">
              {files.length} docs
            </span>
          </div>

          {/* Real-time Search Box */}
          <div className="relative mb-5 lg:mb-0">
            <Search size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar documento..."
              className="w-full bg-[#030816] border border-white/10 rounded-xl pl-11 pr-10 py-3 lg:py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition-all"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1"
              >
                <X size={16} />
              </button>
            )}
          </div>

          {/* Accordion Categories Navigation */}
          <nav className="flex flex-col gap-4 lg:gap-3 flex-1 overflow-y-auto pr-2 custom-scrollbar">
            {categoryKeys.length === 0 ? (
              <p className="text-sm text-slate-500 py-4 text-center">Nenhum documento encontrado.</p>
            ) : (
              categoryKeys.map(catKey => {
                const catTitle = CATEGORY_NAMES[catKey] || catKey;
                const catFiles = categoriesMap[catKey] || [];
                const isOpen = searchQuery.trim() !== '' || !!openCategories[catKey];

                return (
                  <div key={catKey} className="flex flex-col gap-1.5">
                    {/* Category Header Button */}
                    <button
                      onClick={() => toggleCategory(catKey)}
                      className="flex items-center justify-between p-2.5 lg:p-2 rounded-lg hover:bg-white/5 text-slate-200 hover:text-white transition-colors text-sm font-semibold tracking-wide uppercase group text-left"
                    >
                      <div className="flex items-center gap-3 lg:gap-2">
                        {isOpen ? (
                          <FolderOpen size={20} className="text-cyan-400 flex-shrink-0" />
                        ) : (
                          <Folder size={20} className="text-slate-400 group-hover:text-cyan-400 flex-shrink-0 transition-colors" />
                        )}
                        <span className="leading-tight">{catTitle}</span>
                      </div>
                      <div className="flex items-center gap-2 lg:gap-1.5 flex-shrink-0">
                        <span className="text-xs font-mono text-slate-400 bg-white/5 px-2 lg:px-1.5 py-0.5 rounded">
                          {catFiles.length}
                        </span>
                        {isOpen ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-500" />}
                      </div>
                    </button>

                    {/* Collapsible Documents List */}
                    {isOpen && (
                      <div className="flex flex-col gap-1 pl-4 ml-2.5 border-l border-white/10">
                        {catFiles.map(file => {
                          const isActive = currentPath === file.path;
                          return (
                            <Link
                              key={file.path}
                              href={`?doc=${encodeURIComponent(file.path)}`}
                              onClick={() => setIsMobileMenuOpen(false)}
                              className={`flex items-start justify-between p-2.5 lg:p-2 rounded-lg text-sm transition-all duration-200 group ${
                                isActive
                                  ? 'bg-cyan-500/15 text-cyan-300 font-semibold border border-cyan-500/30 shadow-[inset_0_0_12px_rgba(6,182,212,0.08)]'
                                  : 'text-slate-300 hover:bg-white/5 hover:text-white font-medium'
                              }`}
                            >
                              <div className="flex items-start gap-2.5 lg:gap-2">
                                <FileText size={18} className={`mt-0.5 flex-shrink-0 ${isActive ? 'text-cyan-400 opacity-100' : 'text-slate-400 opacity-80 group-hover:opacity-100 group-hover:text-cyan-400'}`} />
                                <span className="leading-snug" title={file.title}>{file.title}</span>
                              </div>
                              <div className="flex items-center gap-1.5 flex-shrink-0">
                                {file.isPdf && (
                                  <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">
                                    PDF
                                  </span>
                                )}
                                {isActive && <ChevronRight size={16} className="text-cyan-400 flex-shrink-0" />}
                              </div>
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
