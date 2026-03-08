function escapeHtml(value: string): string {
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function escapeAttribute(value: string): string {
    return escapeHtml(value).replaceAll('`', '&#96;');
}

function sanitizeHref(rawHref: string): string | null {
    const trimmed = rawHref.trim();
    if (!trimmed) {
        return null;
    }

    if (trimmed.startsWith('#') || trimmed.startsWith('/')) {
        return trimmed;
    }

    try {
        const url = new URL(trimmed);
        if (url.protocol === 'http:' || url.protocol === 'https:' || url.protocol === 'mailto:') {
            return trimmed;
        }
    } catch {
        return null;
    }

    return null;
}

function renderInlineMarkdown(value: string): string {
    const codePlaceholders: string[] = [];
    let html = escapeHtml(value);

    html = html.replace(/`([^`]+)`/g, (_, code: string) => {
        const placeholder = `@@CODE_${codePlaceholders.length}@@`;
        codePlaceholders.push(`<code>${code}</code>`);
        return placeholder;
    });

    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label: string, href: string) => {
        const safeHref = sanitizeHref(href);
        const renderedLabel = renderInlineMarkdown(label);
        if (safeHref === null) {
            return renderedLabel;
        }
        const isExternal = safeHref.startsWith('http://') || safeHref.startsWith('https://');
        const rel = isExternal ? ' rel="noreferrer noopener"' : '';
        const target = isExternal ? ' target="_blank"' : '';
        return `<a href="${escapeAttribute(safeHref)}"${target}${rel}>${renderedLabel}</a>`;
    });

    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

    for (let index = 0; index < codePlaceholders.length; index += 1) {
        html = html.replace(`@@CODE_${index}@@`, codePlaceholders[index]);
    }

    return html;
}

function renderList(items: string[], tagName: 'ul' | 'ol'): string {
    const renderedItems = items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join('');
    return `<${tagName}>${renderedItems}</${tagName}>`;
}

function renderParagraph(lines: string[]): string {
    const text = lines.join(' ').trim();
    if (!text) {
        return '';
    }
    return `<p>${renderInlineMarkdown(text)}</p>`;
}

function renderBlockquote(lines: string[]): string {
    const inner = lines
        .map((line) => line.replace(/^>\s?/, '').trim())
        .filter(Boolean)
        .map((line) => `<p>${renderInlineMarkdown(line)}</p>`)
        .join('');
    return inner ? `<blockquote>${inner}</blockquote>` : '';
}

function renderCodeBlock(lines: string[], language: string): string {
    const body = escapeHtml(lines.join('\n'));
    const languageBadge = language ? `<div class="code-language">${escapeHtml(language)}</div>` : '';
    return `<pre>${languageBadge}<code>${body}</code></pre>`;
}

export function renderRichMarkdown(markdown: string | null | undefined): string {
    if (!markdown || !markdown.trim()) {
        return '';
    }

    const lines = markdown.replaceAll('\r\n', '\n').split('\n');
    const blocks: string[] = [];
    let index = 0;

    while (index < lines.length) {
        const line = lines[index];
        const trimmed = line.trim();

        if (!trimmed) {
            index += 1;
            continue;
        }

        const codeFence = trimmed.match(/^```([\w-]+)?\s*$/);
        if (codeFence) {
            const language = codeFence[1] ?? '';
            index += 1;
            const codeLines: string[] = [];
            while (index < lines.length && !lines[index].trim().startsWith('```')) {
                codeLines.push(lines[index]);
                index += 1;
            }
            if (index < lines.length) {
                index += 1;
            }
            blocks.push(renderCodeBlock(codeLines, language));
            continue;
        }

        const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
        if (heading) {
            const level = heading[1].length;
            blocks.push(`<h${level}>${renderInlineMarkdown(heading[2].trim())}</h${level}>`);
            index += 1;
            continue;
        }

        if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
            blocks.push('<hr />');
            index += 1;
            continue;
        }

        if (trimmed.startsWith('>')) {
            const quoteLines: string[] = [];
            while (index < lines.length && lines[index].trim().startsWith('>')) {
                quoteLines.push(lines[index]);
                index += 1;
            }
            blocks.push(renderBlockquote(quoteLines));
            continue;
        }

        if (/^[-*]\s+/.test(trimmed)) {
            const items: string[] = [];
            while (index < lines.length) {
                const current = lines[index].trim();
                const match = current.match(/^[-*]\s+(.*)$/);
                if (!match) {
                    break;
                }
                items.push(match[1]);
                index += 1;
            }
            blocks.push(renderList(items, 'ul'));
            continue;
        }

        if (/^\d+\.\s+/.test(trimmed)) {
            const items: string[] = [];
            while (index < lines.length) {
                const current = lines[index].trim();
                const match = current.match(/^\d+\.\s+(.*)$/);
                if (!match) {
                    break;
                }
                items.push(match[1]);
                index += 1;
            }
            blocks.push(renderList(items, 'ol'));
            continue;
        }

        const paragraphLines: string[] = [];
        while (index < lines.length) {
            const current = lines[index].trim();
            if (
                !current ||
                /^```/.test(current) ||
                /^(#{1,6})\s+/.test(current) ||
                /^(-{3,}|\*{3,})$/.test(current) ||
                current.startsWith('>') ||
                /^[-*]\s+/.test(current) ||
                /^\d+\.\s+/.test(current)
            ) {
                break;
            }
            paragraphLines.push(current);
            index += 1;
        }
        blocks.push(renderParagraph(paragraphLines));
    }

    return blocks.filter(Boolean).join('');
}
