'use client';

import React from 'react';
import { Info, AlertTriangle, Lightbulb, AlertCircle, ShieldAlert } from 'lucide-react';

interface AdmonitionBlockProps {
  children?: React.ReactNode;
}

export default function AdmonitionBlock({ children }: AdmonitionBlockProps) {
  // Extrai o texto puro para detectar padrão GitHub: [!NOTE], [!TIP], etc.
  const extractText = (node: any): string => {
    if (typeof node === 'string') return node;
    if (Array.isArray(node)) return node.map(extractText).join('');
    if (node && typeof node === 'object' && node.props && node.props.children) {
      return extractText(node.props.children);
    }
    return '';
  };

  const rawText = extractText(children).trim();
  const noteMatch = rawText.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/i);

  if (noteMatch) {
    const type = noteMatch[1].toUpperCase();

    const config = {
      NOTE: {
        icon: Info,
        title: 'Nota',
        border: 'border-l-sky-500',
        bg: 'bg-sky-950/20',
        text: 'text-sky-300',
      },
      TIP: {
        icon: Lightbulb,
        title: 'Dica',
        border: 'border-l-emerald-500',
        bg: 'bg-emerald-950/20',
        text: 'text-emerald-300',
      },
      IMPORTANT: {
        icon: AlertCircle,
        title: 'Importante',
        border: 'border-l-indigo-500',
        bg: 'bg-indigo-950/20',
        text: 'text-indigo-300',
      },
      WARNING: {
        icon: AlertTriangle,
        title: 'Atenção',
        border: 'border-l-amber-500',
        bg: 'bg-amber-950/20',
        text: 'text-amber-300',
      },
      CAUTION: {
        icon: ShieldAlert,
        title: 'Cuidado',
        border: 'border-l-rose-500',
        bg: 'bg-rose-950/20',
        text: 'text-rose-300',
      },
    }[type] || {
      icon: Info,
      title: 'Nota',
      border: 'border-l-sky-500',
      bg: 'bg-sky-950/20',
      text: 'text-sky-300',
    };

    const Icon = config.icon;

    // Remove o marcador [!TIPO] dos filhos para exibição limpa
    const cleanChildren = React.Children.map(children, (child) => {
      if (typeof child === 'string') {
        const cleaned = child.replace(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i, '');
        return cleaned || null;
      }
      if (React.isValidElement(child) && child.props && child.props.children) {
        const childText = extractText(child.props.children);
        if (childText.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/i)) {
          const innerCleaned = childText.replace(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i, '');
          return React.cloneElement(child as React.ReactElement<any>, {
            children: innerCleaned,
          });
        }
      }
      return child;
    });

    return (
      <div
        className={`my-5 border-l-2 ${config.border} ${config.bg} rounded-r-lg px-4 py-3 text-sm text-slate-300`}
      >
        <div className={`flex items-center gap-1.5 mb-1.5 font-mono text-xs font-semibold uppercase tracking-wider ${config.text}`}>
          <Icon size={14} />
          <span>{config.title}</span>
        </div>
        <div className="leading-relaxed [&>p]:mb-2 [&>p:last-child]:mb-0">
          {cleanChildren}
        </div>
      </div>
    );
  }

  // Citação editorial padrão
  return (
    <blockquote className="my-5 border-l-2 border-slate-700 bg-slate-900/30 px-4 py-2.5 rounded-r-lg text-slate-300 text-sm leading-relaxed not-italic">
      {children}
    </blockquote>
  );
}
