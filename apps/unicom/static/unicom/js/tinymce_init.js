/*
 * Global utility to initialise TinyMCE editors across the Unicom admin.
 * Usage:
 *   UnicomTinyMCE.init('#selector', {
 *       // Any TinyMCE config overrides.
 *       setup: function (editor) {
 *           // Called when the editor instance is ready.
 *       }
 *   });
 */
(function (global) {
    'use strict';

    if (!global) {
        return;
    }

    let templateVariablePromise = null;
    let templateVariables = [];
    let templateVariablesEnabled = false;
    const VARIABLE_CLASS = 'unicom-template-variable';
    const VARIABLE_REGEX = /\{\{\s*variables\.[^}]+\s*\}\}/g;

    function preloadTemplateVariables() {
        if (templateVariablePromise) {
            return templateVariablePromise;
        }

        if (typeof fetch !== 'function') {
            templateVariables = [];
            templateVariablesEnabled = false;
            templateVariablePromise = Promise.resolve(null);
            return templateVariablePromise;
        }

        templateVariablePromise = fetch('/unicrm/api/template-variables/')
            .then(function (response) {
                if (response.status === 404) {
                    templateVariables = [];
                    templateVariablesEnabled = false;
                    return null;
                }
                if (!response.ok) {
                    throw new Error('Failed to load template variables');
                }
                return response.json().then(function (data) {
                    if (!Array.isArray(data)) {
                        throw new Error('Unexpected template variables payload');
                    }
                    templateVariables = data;
                    templateVariablesEnabled = true;
                    return templateVariables;
                });
            })
            .catch(function (err) {
                if (err) {
                    console.info('Template variables unavailable:', err.message || err);
                }
                templateVariables = [];
                templateVariablesEnabled = false;
                return null;
            });

        return templateVariablePromise;
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function extractVariableKey(placeholder) {
        const match = (placeholder || '').match(/\{\{\s*variables\.([^}\s]+)\s*\}\}/);
        return match ? match[1] : '';
    }

    function renderVariablePlaceholder(placeholder) {
        const safePlaceholder = escapeHtml(placeholder);
        const displayKey = extractVariableKey(placeholder);
        const displayText = displayKey ? 'variables.' + displayKey : placeholder;
        return '<code class="' + VARIABLE_CLASS + '" data-template-variable="' + safePlaceholder + '">' + escapeHtml(displayText) + '</code>';
    }

    function convertHtmlPlaceholdersToCode(html) {
        if (!html) {
            return html;
        }
        const cleaned = decodeProtectedPlaceholders(revertVariableCodeToPlaceholder(html));
        return cleaned.replace(VARIABLE_REGEX, function (match) {
            return renderVariablePlaceholder(match);
        });
    }

    function revertVariableCodeToPlaceholder(html) {
        if (!html) {
            return html;
        }
        const pattern = new RegExp(
            '<code[^>]*class="[^"]*' + VARIABLE_CLASS + '[^"]*"[^>]*data-template-variable="([^"]*)"[^>]*>[\\s\\S]*?<\\/code>',
            'gi'
        );
        return html.replace(pattern, function (_, placeholder) {
            return placeholder.replace(/&amp;/g, '&')
                .replace(/&lt;/g, '<')
                .replace(/&gt;/g, '>')
                .replace(/&quot;/g, '"')
                .replace(/&#39;/g, "'");
        });
    }

    function decodeProtectedPlaceholders(html) {
        return html.replace(/<!--\s*mce:protected\s+([^>]+?)-->/gi, function (_, encoded) {
            const trimmed = (encoded || '').trim();
            if (!trimmed) {
                return '';
            }
            try {
                return decodeURIComponent(trimmed);
            } catch (err) {
                return trimmed;
            }
        });
    }

    function registerVariablesMenu(ed) {
        if (!templateVariablesEnabled) {
            return;
        }

        const variables = templateVariables.slice();
        ed.ui.registry.addMenuButton('unicom_variables', {
            text: 'Variables',
            tooltip: 'Insert template variables',
            fetch: function (callback) {
                if (!variables.length) {
                    callback([{
                        type: 'menuitem',
                        text: 'No variables configured',
                        enabled: false
                    }]);
                    return;
                }
                const items = variables.map(function (variable) {
                    return {
                        type: 'menuitem',
                        text: variable.label,
                        tooltip: variable.description || variable.placeholder,
                        onAction: function () {
                            ed.insertContent(renderVariablePlaceholder(variable.placeholder));
                        }
                    };
                });
                callback(items);
            }
        });
    }

    function removeToolbarControl(toolbarConfig, controlName) {
        if (!toolbarConfig) {
            return toolbarConfig;
        }

        if (Array.isArray(toolbarConfig)) {
            return toolbarConfig
                .map(function (entry) {
                    return removeToolbarControl(entry, controlName);
                })
                .filter(function (entry) {
                    if (typeof entry === 'string') {
                        return entry.length > 0;
                    }
                    return Boolean(entry);
                });
        }

        if (typeof toolbarConfig === 'string') {
            const cleanedGroups = toolbarConfig
                .split('|')
                .map(function (group) {
                    const items = group
                        .split(/\s+/)
                        .filter(Boolean)
                        .filter(function (item) {
                            return item !== controlName;
                        });
                    return items.join(' ');
                })
                .filter(function (group) {
                    return group.trim().length > 0;
                });
            return cleanedGroups.join(cleanedGroups.length ? ' | ' : '');
        }

        return toolbarConfig;
    }

    // Preload variables so the fetch happens before any editor renders.
    preloadTemplateVariables();

    const DEFAULT_CONFIG = {
        plugins: 'link image lists table code unicom_ai_template',
        toolbar: 'undo redo | blocks | bold italic | alignleft aligncenter alignright | indent outdent | bullist numlist | code | table | unicom_variables | unicom_ai_template',
        menubar: 'file edit view insert format tools table',
        convert_urls: false,
        height: 400,
        max_height: 400,
        branding: false,
        promotion: false,
        paste_webkit_styles: 'all',
        content_css: [
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css'
        ],
        content_style: [
            'code.' + VARIABLE_CLASS + ' {',
            '  background:#e3f2fd;',
            '  color:#0d47a1;',
            '  padding:1px 3px;',
            '  border-radius:3px;',
            '  font-family:monospace;',
            '  font-size:0.95em;',
            '  white-space:nowrap;',
            '}',
            'code.' + VARIABLE_CLASS + '::before {',
            '  content:"{{ ";',
            '  color:#0d47a1;',
            '}',
            'code.' + VARIABLE_CLASS + '::after {',
            '  content:" }}";',
            '  color:#0d47a1;',
            '}'
        ].join('\n'),
        extended_valid_elements: 'i[class|style],span[class|style],code[class|data-template-variable]',
        /*
         * We will attach a default setup that triggers save on change so that the underlying
         * <textarea> is always kept in sync.
         */
        setup: function (ed) {
            registerVariablesMenu(ed);

            ed.on('BeforeSetContent', function (e) {
                if (e.content) {
                    e.content = convertHtmlPlaceholdersToCode(
                        e.content.replace(
                            /<(i|span)([^>]*)><\/\1>/g,
                            '<$1$2> </$1>'
                        )
                    );
                }
            });

            ed.on('BeforeGetContent', function (e) {
                if (e.content) {
                    e.content = revertVariableCodeToPlaceholder(e.content);
                }
            });

            ed.on('GetContent', function (e) {
                if (e.content) {
                    e.content = revertVariableCodeToPlaceholder(e.content);
                }
            });

            ed.on('SaveContent', function (e) {
                if (e.content) {
                    e.content = revertVariableCodeToPlaceholder(e.content);
                }
            });

            // Patch: ensure empty inline tags keep a space and template variables stay readable.
            // Existing change-save sync
            ed.on('change', function () {
                ed.save();
            });
        }
    };

    function mergeConfigs(base, overrides) {
        if (!overrides) return Object.assign({}, base);

        const merged = Object.assign({}, base, overrides);

        // If user supplied a custom setup, wrap it so both run.
        if (typeof overrides.setup === 'function') {
            const userSetup = overrides.setup;
            merged.setup = function (ed) {
                if (typeof base.setup === 'function') {
                    base.setup(ed);
                }
                userSetup(ed);
            };
        }

        return merged;
    }

    function removeExisting(selector) {
        // Remove any editor targeting the same element (if one already exists).
        if (!global.tinymce || !global.tinymce.editors) return;
        // Iterate over a copy of the array in case removing an editor modifies the collection.
        [...global.tinymce.editors].forEach(function (ed) {
            if (ed.targetElm && ('#' + ed.targetElm.id) === selector) {
                ed.remove();
            }
        });
    }

    function init(selector, overrides) {
        function actuallyInit() {
            return preloadTemplateVariables().then(function () {
                removeExisting(selector);
                const config = mergeConfigs(DEFAULT_CONFIG, overrides);
                if (!templateVariablesEnabled) {
                    config.toolbar = removeToolbarControl(config.toolbar, 'unicom_variables');
                }
                // Ensure selector always matches passed element.
                config.selector = selector;
                config.protect = (config.protect || []).concat([
                    /\{#[\s\S]*?#\}/g,  // Jinja comments
                    /\{\{[\s\S]*?\}\}/g,
                    /\{%[\s\S]*?%\}/g
                ]);
                return global.tinymce.init(config);
            });
        }

        // TinyMCE may not be loaded yet if our helper is referenced before the CDN script executes.
        if (global.tinymce && global.tinymce.init) {
            return actuallyInit();
        }

        // Otherwise, poll a few times until TinyMCE becomes available.
        return new Promise(function (resolve, reject) {
            const maxAttempts = 50; // ±5 seconds at 100 ms interval
            let attempts = 0;
            const interval = setInterval(function () {
                if (global.tinymce && global.tinymce.init) {
                    clearInterval(interval);
                    resolve(actuallyInit());
                } else if (++attempts >= maxAttempts) {
                    clearInterval(interval);
                    console.error('TinyMCE did not load in time.');
                    reject(new Error('TinyMCE not loaded'));
                }
            }, 100);
        });
    }

    // Auto-initialize TinyMCE on elements with data-tinymce attribute
    function initializeAll() {
        const elements = document.querySelectorAll('textarea[data-tinymce]');
        elements.forEach(function(element) {
            init('#' + element.id);
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeAll);
    } else {
        initializeAll();
    }

    // Re-initialize when Django's admin adds a new inline form
    document.addEventListener('formset:added', function(e) {
        const elements = e.target.querySelectorAll('textarea[data-tinymce]');
        elements.forEach(function(element) {
            init('#' + element.id);
        });
    });

    global.UnicomTinyMCE = {
        init: init,
        defaultConfig: DEFAULT_CONFIG,
        initializeAll: initializeAll
    };
})(window); 
