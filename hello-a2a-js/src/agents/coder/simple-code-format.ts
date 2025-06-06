/**
 * Simple code format handling for Ollama-based code generation
 */

export interface CodeFile {
    filename: string;
    content: string;
}

export interface CodeMessage {
    files: CodeFile[];
}

/**
 * Parse code blocks from Ollama response text
 */
export function parseCodeFromText(text: string): CodeMessage {
    const files: CodeFile[] = [];
    const codeBlockRegex = /```(\w+)?\s*(?:\/\/\s*(.+))?\n([\s\S]*?)```/g;
    let match;
    let fileIndex = 1;

    while ((match = codeBlockRegex.exec(text)) !== null) {
        const language = match[1] || 'txt';
        const comment = match[2];
        const content = match[3].trim();

        // Try to extract filename from comment or use a default
        let filename = `file${fileIndex}.${getFileExtension(language)}`;
        if (comment) {
            const filenameMatch = comment.match(/(?:filename:|file:)\s*(.+)/i);
            if (filenameMatch) {
                filename = filenameMatch[1].trim();
            } else if (comment.includes('.')) {
                filename = comment.trim();
            }
        }

        files.push({ filename, content });
        fileIndex++;
    }

    // If no code blocks found, treat the entire response as a single file
    if (files.length === 0 && text.trim()) {
        files.push({
            filename: 'output.txt',
            content: text.trim()
        });
    }

    return { files };
}

function getFileExtension(language: string): string {
    const extensions: Record<string, string> = {
        'javascript': 'js',
        'typescript': 'ts',
        'python': 'py',
        'java': 'java',
        'c': 'c',
        'cpp': 'cpp',
        'csharp': 'cs',
        'go': 'go',
        'rust': 'rs',
        'php': 'php',
        'ruby': 'rb',
        'html': 'html',
        'css': 'css',
        'json': 'json',
        'xml': 'xml',
        'yaml': 'yml',
        'yml': 'yml',
        'markdown': 'md',
        'md': 'md',
        'sh': 'sh',
        'bash': 'sh',
        'sql': 'sql',
    };

    return extensions[language.toLowerCase()] || 'txt';
}
