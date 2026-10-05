'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { BookOpen, Search, Folder, FolderOpen, FileText, ChevronRight, ChevronDown, X } from 'lucide-react';

export interface MarkdownFile {
  path: string;
  title: string;
  category: string;
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
    <div className="bg-white/5 border border-white/10 rounded-2xl p-5 backdrop-blur-md shadow-2xl flex flex-col gap-4">
      {/* Sidebar Header */}
      <div className="flex items-center justify-between pb-3 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <BookOpen className="text-cyan-400" size={18} />
          <h2 className="text-sm font-bold tracking-wider text-slate-200 uppercase">Documentação</h2>
        </div>
        <span className="text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 px-2 py-0.5 rounded-full font-medium">
          {files.length} docs
        </span>
      </div>

      {/* Real-time Search Box */}
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Buscar documento..."
          className="w-full bg-[#030816] border border-white/10 rounded-xl pl-9 pr-8 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition-all"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-0.5"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {/* Accordion Categories Navigation */}
      <nav className="flex flex-col gap-3 max-h-[60vh] overflow-y-auto pr-1 custom-scrollbar">
        {categoryKeys.length === 0 ? (
          <p className="text-xs text-slate-500 py-4 text-center">Nenhum documento encontrado.</p>
        ) : (
          categoryKeys.map(catKey => {
            const catTitle = CATEGORY_NAMES[catKey] || catKey;
            const catFiles = categoriesMap[catKey] || [];
            const isOpen = searchQuery.trim() !== '' || !!openCategories[catKey];

            return (
              <div key={catKey} className="flex flex-col gap-1">
                {/* Category Header Button */}
                <button
                  onClick={() => toggleCategory(catKey)}
                  className="flex items-center justify-between p-2 rounded-lg hover:bg-white/5 text-slate-300 hover:text-white transition-colors text-xs font-semibold tracking-wide uppercase group text-left"
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    {isOpen ? (
                      <FolderOpen size={15} className="text-cyan-400 flex-shrink-0" />
                    ) : (
                      <Folder size={15} className="text-slate-400 group-hover:text-cyan-400 flex-shrink-0 transition-colors" />
                    )}
                    <span className="truncate">{catTitle}</span>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <span className="text-[10px] font-mono text-slate-500 bg-white/5 px-1.5 py-0.2 rounded">
                      {catFiles.length}
                    </span>
                    {isOpen ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-500" />}
                  </div>
                </button>

                {/* Collapsible Documents List */}
                {isOpen && (
                  <div className="flex flex-col gap-0.5 pl-3 ml-2 border-l border-white/10">
                    {catFiles.map(file => {
                      const isActive = currentPath === file.path;
                      return (
                        <Link
                          key={file.path}
                          href={`?doc=${encodeURIComponent(file.path)}`}
                          className={`flex items-center justify-between p-2 rounded-lg text-xs transition-all duration-200 group ${
                            isActive
                              ? 'bg-cyan-500/15 text-cyan-300 font-semibold border border-cyan-500/30 shadow-[inset_0_0_12px_rgba(6,182,212,0.08)]'
                              : 'text-slate-400 hover:bg-white/5 hover:text-slate-200 font-medium'
                          }`}
                        >
                          <div className="flex items-center gap-2 overflow-hidden">
                            <FileText size={14} className={`flex-shrink-0 ${isActive ? 'text-cyan-400 opacity-100' : 'opacity-40 group-hover:opacity-100'}`} />
                            <span className="truncate" title={file.title}>{file.title}</span>
                          </div>
                          {isActive && <ChevronRight size={14} className="text-cyan-400 flex-shrink-0" />}
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
  );
}
