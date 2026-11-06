'use client';

import React, { useState } from 'react';
import { Check, Copy, Terminal } from 'lucide-react';
import MermaidBlock from './MermaidBlock';

interface CodeBlockProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export default function CodeBlock({ children, className, ...props }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  // Extrai a linguagem a partir de className (ex.: "language-python")
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1].toLowerCase() : '';

  // Extrai o texto puro
  const extractText = (node: any): string => {
    if (typeof node === 'string') return node;
    if (Array.isArray(node)) return node.map(extractText).join('');
    if (node && typeof node === 'object' && node.props && node.props.children) {
      return extractText(node.props.children);
    }
    return '';
  };

  const rawCode = extractText(children).replace(/\n$/, '');

  // Trata diagramas Mermaid
  if (language === 'mermaid') {
    return <MermaidBlock code={rawCode} />;
  }

  // Código inline
  if (!className && !match && typeof children === 'string' && !children.includes('\n')) {
    return (
      <code
        className="text-sky-300 bg-slate-800/70 px-1.5 py-0.5 rounded border border-slate-700/60 font-mono text-[13px] font-normal"
        {...props}
      >
        {children}
      </code>
    );
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(rawCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Falha ao copiar:', err);
    }
  };

  return (
    <div className="my-5 rounded-lg border border-slate-800/90 bg-[#07090E] overflow-hidden">
      {/* Header Bar Editorial e Institucional (sem janelas falsas de SO) */}
      <div className="flex items-center justify-between border-b border-slate-800/80 bg-[#0C101A] px-3.5 py-2 text-xs font-mono">
        <div className="flex items-center gap-2 text-slate-400">
          <Terminal size={12} className="text-sky-400" />
          <span className="text-[11px] uppercase tracking-wider font-semibold">
            {language || 'texto'}
          </span>
        </div>

        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 hover:text-white border border-slate-700/60 text-[11px] transition-colors"
          title="Copiar código"
        >
          {copied ? (
            <>
              <Check size={12} className="text-emerald-400" />
              <span className="text-emerald-400 font-sans font-medium">Copiado</span>
            </>
          ) : (
            <>
              <Copy size={12} className="text-slate-400" />
              <span className="font-sans">Copiar</span>
            </>
          )}
        </button>
      </div>

      {/* Bloco de Código */}
      <div className="overflow-x-auto p-4 text-[13.5px] leading-relaxed font-mono text-slate-200">
        <pre className="!bg-transparent !p-0 !m-0 !border-0 font-mono text-slate-200">
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
      </div>
    </div>
  );
}
