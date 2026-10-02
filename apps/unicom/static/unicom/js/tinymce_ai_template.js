// TinyMCE AI Template Button and Modal Integration for Unicom
(function(global) {
    'use strict';
    if (!global) return;

    // Utility to show/hide the global loading overlay
    function showLoading(text) {
        var overlay = document.querySelector('.global-loading-overlay');
        if (overlay) {
            overlay.querySelector('.loading-text').textContent = text || 'Loading...';
            overlay.classList.remove('hidden');
        }
    }
    function hideLoading() {
        var overlay = document.querySelector('.global-loading-overlay');
        if (overlay) overlay.classList.add('hidden');
    }

    // Helper to fetch templates from API
    function fetchTemplates() {
        return fetch('/unicom/api/message-templates/')
            .then(r => r.json());
    }

    // Helper to call AI populate API
    function populateTemplate(templateId, htmlPrompt, model) {
        return fetch('/unicom/api/message-templates/populate/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({template_id: templateId, html_prompt: htmlPrompt, model: model})
        }).then(r => r.json());
    }

    // Modal logic
    function setupModal(mainEditor) {
        var modalEl = document.getElementById('unicom-ai-template-modal');
        if (!modalEl) return;
        var select = document.getElementById('unicom-ai-template-select');
        var preview = document.getElementById('unicom-ai-template-preview');
        var customPreview = document.getElementById('unicom-ai-template-custom-preview');
        var promptTextarea = document.getElementById('unicom-ai-template-prompt');
        var generateBtn = document.getElementById('unicom-ai-template-generate');
        var insertBtn = document.getElementById('unicom-ai-template-insert');
        var originalCollapse = document.getElementById('unicom-ai-template-original-collapse');
        var originalToggleText = document.getElementById('unicom-ai-template-original-toggle-text');
        
        var bootstrapModal = null;
        var bsCollapse = null;
        var templatesList = [];
        var customizedHtml = '';
        var firstGeneration = true;

        if (window.bootstrap) {
            if (window.bootstrap.Modal) {
                bootstrapModal = bootstrap.Modal.getOrCreateInstance(modalEl);
            }
            if (window.bootstrap.Collapse && originalCollapse) {
                bsCollapse = bootstrap.Collapse.getOrCreateInstance(originalCollapse);
            }
        }

        // Helper to update preview
        function updatePreview() {
            var val = select.value;
            var tmpl = templatesList.find(t => (t.id || t.title) == val);
            preview.innerHTML = tmpl ? tmpl.content : '<em>No template selected.</em>';
            customPreview.innerHTML = '';
            customizedHtml = '';
            
            // Enable insert button if template is selected (allow manual insertion)
            insertBtn.disabled = !tmpl;
            
            // Per user request, always expand the preview when it's updated.
            if (bsCollapse) {
                bsCollapse.show();
            }
        }

        // On modal show: fetch templates and init TinyMCE for prompt
        modalEl.addEventListener('show.bs.modal', function() {
            showLoading('Loading templates...');
            fetchTemplates().then(function(templates) {
                templatesList = templates;
                select.innerHTML = '';
                templates.forEach(function(tmpl) {
                    var opt = document.createElement('option');
                    opt.value = tmpl.id || tmpl.title;
                    opt.textContent = tmpl.title;
                    select.appendChild(opt);
                });
                hideLoading();
                updatePreview(); // This now also handles showing the preview
                firstGeneration = true;
            }).catch(function() {
                select.innerHTML = '<option value="">Error loading templates</option>';
                preview.innerHTML = '<em>Error loading templates.</em>';
                customPreview.innerHTML = '';
                customizedHtml = '';
                insertBtn.disabled = true;
                hideLoading();
            });

            // Init TinyMCE for prompt
            if (global.tinymce && global.UnicomTinyMCE && global.UnicomTinyMCE.init) {
                global.UnicomTinyMCE.init('#unicom-ai-template-prompt', {
                    height: 200,
                    menubar: false,
                    toolbar: 'undo redo | bold italic | bullist numlist',
                });
            }
        });

        // Update preview on template change
        select.addEventListener('change', updatePreview);

        // Collapse toggle text logic
        if (originalCollapse) {
            originalCollapse.addEventListener('show.bs.collapse', function() {
                if (originalToggleText) originalToggleText.textContent = 'Hide';
            });
            originalCollapse.addEventListener('hide.bs.collapse', function() {
                if (originalToggleText) originalToggleText.textContent = 'Show';
            });
        }

        // On modal hide: remove TinyMCE instance for prompt and reset state
        modalEl.addEventListener('hidden.bs.modal', function() {
            if (global.tinymce) {
                var ed = global.tinymce.get('unicom-ai-template-prompt');
                if (ed) ed.remove();
            }
            promptTextarea.value = '';
            preview.innerHTML = '';
            customPreview.innerHTML = '';
            customizedHtml = '';
            insertBtn.disabled = true;
            
            // Explicitly show the original preview to reset it for the next open
            if(bsCollapse) {
                bsCollapse.show();
            }
        });

        // Generate button logic
        generateBtn.addEventListener('click', function() {
            var templateId = select.value;
            var modelSelect = document.getElementById('unicom-ai-template-model-select');
            var selectedModel = modelSelect ? modelSelect.value : '';
            
            if (!templateId) {
                alert('Please select a template.');
                return;
            }
            
            if (!selectedModel) {
                alert('Please select an AI model to generate customized content.');
                return;
            }
            
            var promptHtml = '';
            if (global.tinymce) {
                var ed = global.tinymce.get('unicom-ai-template-prompt');
                promptHtml = ed ? ed.getContent() : promptTextarea.value;
            } else {
                promptHtml = promptTextarea.value;
            }
            
            showLoading('Generating...');
            customizedHtml = '';
            customPreview.innerHTML = '<em>Generating...</em>';
            
            populateTemplate(templateId, promptHtml, selectedModel).then(function(resp) {
                hideLoading();
                if (resp && resp.html) {
                    customPreview.innerHTML = resp.html;
                    customizedHtml = resp.html;
                    // Collapse original preview after first generation
                    if (firstGeneration && bsCollapse) {
                        bsCollapse.hide();
                        firstGeneration = false;
                    }
                } else {
                    const errorMsg = resp.error || 'Failed to generate template.';
                    customPreview.innerHTML = `<em style="color: red;">Error: ${errorMsg}</em>`;
                    alert(errorMsg);
                }
            }).catch(function() {
                hideLoading();
                const errorMsg = 'An unexpected error occurred.';
                customPreview.innerHTML = `<em style="color: red;">Error: ${errorMsg}</em>`;
                alert(errorMsg);
            });
        });

        // Insert button logic
        insertBtn.addEventListener('click', function() {
            var templateId = select.value;
            var tmpl = templatesList.find(t => (t.id || t.title) == templateId);
            
            if (!tmpl) {
                alert('Please select a template.');
                return;
            }
            
            // Use customized HTML if available, otherwise use original template
            var contentToInsert = customizedHtml || tmpl.content;
            
            if (contentToInsert && mainEditor && mainEditor.insertContent) {
                mainEditor.insertContent(contentToInsert);
                if (bootstrapModal) bootstrapModal.hide();
            }
        });
    }

    // Register the custom TinyMCE button
    if (global.tinymce) {
        global.tinymce.PluginManager.add('unicom_ai_template', function(editor) {
            editor.ui.registry.addButton('unicom_ai_template', {
                text: 'AI Template',
                icon: 'template',
                onAction: function() {
                    var modal = document.getElementById('unicom-ai-template-modal');
                    if (modal) {
                        // Setup modal logic on first open
                        if (!modal.dataset.unicomSetup) {
                            setupModal(editor);
                            modal.dataset.unicomSetup = '1';
                        }
                        if (window.bootstrap && window.bootstrap.Modal) {
                            var bsModal = window.bootstrap.Modal.getOrCreateInstance(modal);
                            bsModal.show();
                        } else {
                            modal.style.display = 'block';
                        }
                    }
                }
            });
        });
    }

    // Expose for manual init if needed
    global.UnicomTinyMCEAI = {
        showLoading: showLoading,
        hideLoading: hideLoading
    };
})(window); 