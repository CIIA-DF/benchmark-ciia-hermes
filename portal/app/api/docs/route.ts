import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const fileParam = searchParams.get('file');

  if (!fileParam) {
    return new NextResponse('Parâmetro file ausente', { status: 400 });
  }

  try {
    const docsDir = path.resolve(process.cwd(), '../docs');
    // Normalize and prevent path traversal
    const safePath = path.normalize(fileParam).replace(/^(\.\.(\/|\\|$))+/, '');
    const fullPath = path.resolve(docsDir, safePath);

    if (!fullPath.startsWith(docsDir)) {
      return new NextResponse('Acesso negado', { status: 403 });
    }

    const fileBuffer = await fs.readFile(fullPath);
    const ext = path.extname(fullPath).toLowerCase();

    let contentType = 'application/octet-stream';
    if (ext === '.pdf') {
      contentType = 'application/pdf';
    } else if (ext === '.md' || ext === '.txt') {
      contentType = 'text/plain; charset=utf-8';
    } else if (ext === '.png') {
      contentType = 'image/png';
    } else if (ext === '.jpg' || ext === '.jpeg') {
      contentType = 'image/jpeg';
    } else if (ext === '.svg') {
      contentType = 'image/svg+xml';
    }

    return new NextResponse(fileBuffer, {
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': 'inline',
        'Cache-Control': 'public, max-age=3600',
      },
    });
  } catch (error) {
    console.error('Erro ao servir arquivo de documentação:', error);
    return new NextResponse('Arquivo não encontrado', { status: 404 });
  }
}
