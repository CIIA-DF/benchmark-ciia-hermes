'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Eye, Code2 } from 'lucide-react';

interface MermaidBlockProps {
  code: string;
}

declare global {
  interface Window {
    mermaid?: {
      initialize: (config: any) => void;
      render: (id: string, text: string) => Promise<{ svg: string }>;
    };
  }
}

export default function MermaidBlock({ code }: MermaidBlockProps) {
  const [svgContent, setSvgContent] = useState<string>('');
  const [renderError, setRenderError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'diagram' | 'code'>('diagram');
  const containerRef = useRef<HTMLDivElement>(null);
  const chartId = useRef(`mermaid-${Math.random().toString(36).substring(2, 9)}`);

  useEffect(() => {
    let isMounted = true;

    const renderChart = async () => {
      if (!window.mermaid) {
        // Carrega o script do Mermaid sob demanda via CDN se não estiver no bundle
        const existingScript = document.getElementById('mermaid-script');
        if (!existingScript) {
          const script = document.createElement('script');
          script.id = 'mermaid-script';
          script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
          script.crossOrigin = 'anonymous';
          script.onload = () => {
            if (window.mermaid) {
              window.mermaid.initialize({
                startOnLoad: false,
                theme: 'dark',
                themeVariables: {
                  darkMode: true,
                  background: '#080B11',
                  primaryColor: '#0E1726',
                  primaryTextColor: '#E2E8F0',
                  primaryBorderColor: '#0284C7',
                  lineColor: '#64748B',
                  secondaryColor: '#1E293B',
                  tertiaryColor: '#0F172A',
                  fontSize: '13px',
                  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
                },
              });
              renderChart();
            }
          };
          script.onerror = () => {
            if (isMounted) setRenderError('Não foi possível carregar o visualizador Mermaid.');
          };
          document.head.appendChild(script);
          return;
        } else {
          // Script já existe mas ainda pode estar carregando
          const checkMermaid = setInterval(() => {
            if (window.mermaid) {
              clearInterval(checkMermaid);
              renderChart();
            }
          }, 150);
          setTimeout(() => clearInterval(checkMermaid), 5000);
          return;
        }
      }

      try {
        const { svg } = await window.mermaid.render(chartId.current, code.trim());
        if (isMounted) {
          setSvgContent(svg);
          setRenderError(null);
        }
      } catch (err: any) {
        if (isMounted) {
          setRenderError(err?.message || 'Falha ao renderizar diagrama.');
        }
      }
    };

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [code]);

  return (
    <div className="my-6 border border-slate-800/90 rounded-lg bg-[#080B11] overflow-hidden">
      {/* Header com Abas */}
      <div className="flex items-center justify-between border-b border-slate-800/80 bg-[#0C101A] px-4 py-2">
        <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider font-semibold">
          Diagrama Mermaid
        </span>

        <div className="flex items-center gap-1 bg-[#080B11] p-0.5 rounded border border-slate-800/80 text-xs">
          <button
            type="button"
            onClick={() => setViewMode('diagram')}
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-[11px] transition-colors ${
              viewMode === 'diagram'
                ? 'bg-slate-800 text-sky-400 font-medium'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Eye size={12} />
            <span>Visualizar</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('code')}
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-[11px] transition-colors ${
              viewMode === 'code'
                ? 'bg-slate-800 text-sky-400 font-medium'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Code2 size={12} />
            <span>Código</span>
          </button>
        </div>
      </div>

      {/* Conteúdo */}
      <div className="p-4 overflow-x-auto min-h-[120px] flex items-center justify-center">
        {viewMode === 'code' ? (
          <pre className="w-full text-xs font-mono text-slate-300 bg-[#06080E] p-3 rounded border border-slate-800/60 overflow-x-auto m-0">
            <code>{code}</code>
          </pre>
        ) : renderError ? (
          <div className="text-center py-4">
            <p className="text-xs text-amber-400 mb-2 font-mono">Diagrama em texto:</p>
            <pre className="text-xs font-mono text-slate-400 bg-[#06080E] p-3 rounded border border-slate-800/60 text-left">
              <code>{code}</code>
            </pre>
          </div>
        ) : svgContent ? (
          <div
            ref={containerRef}
            className="w-full flex justify-center [&_svg]:max-w-full [&_svg]:h-auto"
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        ) : (
          <div className="text-xs font-mono text-slate-500 py-6 animate-pulse">
            Carregando diagrama...
          </div>
        )}
      </div>
    </div>
  );
}
