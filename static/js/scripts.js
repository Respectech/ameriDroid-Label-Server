// Global functions
window.printLabel = function() {
    console.log('printLabel called');
    try {
        var form = document.getElementById('labelForm');
        if (!form) {
            console.error('labelForm not found');
            alert('Error: Label form not found');
            return;
        }
        console.log('Form found:', form);
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'action';
        input.value = 'Print Label';
        form.appendChild(input);
        form.action = '/';
        console.log('Submitting form to / with action=Print Label');
        form.submit();
    } catch (error) {
        console.error('Error in printLabel:', error);
        alert('Error submitting print request: ' + error.message);
    }
};

window.saveTemplate = function() {
    console.log('saveTemplate called');
    try {
        var form = document.getElementById('labelForm');
        if (!form) {
            console.error('labelForm not found');
            alert('Error: Label form not found');
            return;
        }
        // Collect form data
        var formData = new FormData(form);
        var config = {};
        formData.forEach((value, key) => {
            // Convert specific fields to appropriate types
            if (['size1', 'size2', 'size3', 'spacing1', 'spacing2', 'length'].includes(key)) {
                config[key] = parseInt(value, 10) || 0; // Parse numbers
            } else if (['bold1', 'italic1', 'underline1', 'bold2', 'italic2', 'underline2', 'bold3', 'italic3', 'underline3'].includes(key)) {
                config[key] = value === 'on' || value === true; // Parse checkboxes
            } else {
                config[key] = value; // Strings and other types
            }
        });
        // Rename length to length_mm for clarity
        if ('length' in config) {
            config.length_mm = config.length;
            delete config.length;
            console.log('Renamed length to length_mm:', config.length_mm);
        } else {
            console.warn('length field missing, setting length_mm to default 100');
            config.length_mm = 100;
        }
        // Get preview image
        var previewImg = document.querySelector('.preview-wrapper img');
        var previewSrc = previewImg ? previewImg.src : '';
        if (!previewSrc) {
            console.warn('Preview image not found, using empty preview');
        }
        // Open save template modal
        var saveModal = bootstrap.Modal.getInstance(document.getElementById('saveTemplateModal')) || new bootstrap.Modal(document.getElementById('saveTemplateModal'));
        // Set hidden inputs
        document.getElementById('templateConfig').value = JSON.stringify(config);
        document.getElementById('templatePreview').value = previewSrc;
        console.log('Template config prepared:', config);
        console.log('Opening saveTemplateModal');
        saveModal.show();
    } catch (error) {
        console.error('Error in saveTemplate:', error);
        alert('Error opening save template modal: ' + error.message);
    }
};

window.restartWebserver = function() {
    console.log('restartWebserver button clicked');
    if (confirm('Are you sure you want to restart the webserver? This will temporarily disrupt access.')) {
        console.log('User confirmed restart, sending POST to /restart');
        fetch('/restart', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            console.log('Fetch response received, status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Parsed JSON response:', data);
            try {
                alert(data.message); // Display the message
                console.log('Alert displayed with message:', data.message);
            } catch (alertError) {
                console.error('Error displaying alert:', alertError);
            }
            if (data.reload || data.redirect) {
                console.log('Reload condition met, scheduling reload to:', data.redirect || '/');
                setTimeout(() => {
                    console.log('Executing reload now');
                    try {
                        window.location.href = (data.redirect || '/') + '?t=' + new Date().getTime();
                        console.log('window.location.href set');
                    } catch (navError) {
                        console.error('Error setting window.location.href:', navError);
                    }
                }, 5000); // Increased to 5 seconds for debugging
            } else {
                console.log('No reload/redirect in response');
            }
        })
        .catch(error => {
            console.error('Error in restartWebserver:', error);
            try {
                alert('Error restarting webserver: ' + error.message);
                console.log('Error alert displayed');
            } catch (alertError) {
                console.error('Error displaying error alert:', alertError);
            }
        });
    } else {
        console.log('User canceled restart');
    }
};

window.updateCodebase = function() {
    console.log('updateCodebase called');
    try {
        if (!confirm('Are you sure you want to update the codebase to the latest version? The server will restart, and this may take a few seconds.')) {
            console.log('Update canceled');
            return;
        }
        console.log('Sending POST to /update_codebase');
        fetch('/update_codebase', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            console.log('Received response from /update_codebase:', response);
            if (!response.ok) {
                return response.text().then(text => {
                    console.error('Error response text:', text);
                    try {
                        const err = JSON.parse(text);
                        throw new Error(err.message || 'Unknown server error');
                    } catch {
                        throw new Error(text || 'Failed to fetch update_codebase');
                    }
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Update response:', data);
            showAlert(data.message, 'success');
            console.log('Success alert triggered:', data.message);
            // Check for reload or redirect instruction
            if (data.reload || data.redirect) {
                console.log('Reloading page after codebase update');
                setTimeout(() => {
                    window.location.href = data.redirect || '/';
                }, 3000); // Delay to allow server restart
            }
        })
        .catch(error => {
            console.error('Error in updateCodebase:', error);
            try {
                showAlert('Error updating codebase: ' + error.message, 'danger');
                console.log('Error alert triggered:', error.message);
            } catch (alertError) {
                console.error('Failed to show alert:', alertError);
                alert('Error updating codebase: ' + error.message);
            }
        });
    } catch (error) {
        console.error('Unexpected error in updateCodebase:', error);
        try {
            showAlert('Unexpected error updating codebase: ' + error.message, 'danger');
            console.log('Unexpected error alert triggered:', error.message);
        } catch (alertError) {
            console.error('Failed to show alert:', alertError);
            alert('Unexpected error updating codebase: ' + error.message);
        }
    }
};

window.selectFont = function(fontName, applyToAll) {
    console.log('selectFont called with:', fontName, applyToAll);
    try {
        let currentTextarea = window.currentTextarea;
        console.log('Current textarea:', currentTextarea);
        if (applyToAll) {
            console.log('Applying font to all textareas');
            document.querySelectorAll('.font-name').forEach(function(element) {
                element.textContent = fontName;
                element.style.fontFamily = fontName;
                let textareaNum = element.getAttribute('data-textarea');
                let faceInput = document.getElementById('face' + textareaNum);
                if (faceInput) {
                    faceInput.value = fontName;
                    console.log(`Updated face${textareaNum} to ${fontName}`);
                } else {
                    console.warn(`face${textareaNum} input not found`);
                }
            });
        } else {
            console.log('Applying font to textarea:', currentTextarea);
            if (!currentTextarea) {
                console.error('No currentTextarea set');
                showAlert('Error: Please select a textarea first', 'danger');
                return;
            }
            var textareaNum = currentTextarea;
            var fontElement = document.querySelector('.font-name[data-textarea="' + textareaNum + '"]');
            if (fontElement) {
                fontElement.textContent = fontName;
                fontElement.style.fontFamily = fontName;
                let faceInput = document.getElementById('face' + textareaNum);
                if (faceInput) {
                    faceInput.value = fontName;
                    console.log(`Updated face${textareaNum} to ${fontName}`);
                } else {
                    console.warn(`face${textareaNum} input not found`);
                }
            } else {
                console.error(`.font-name[data-textarea="${textareaNum}"] not found`);
                showAlert('Error: Font display element not found', 'danger');
            }
        }
        // Close the font modal
        try {
            let modal = bootstrap.Modal.getInstance(document.getElementById('fontModal'));
            if (modal) {
                modal.hide();
                console.log('Font modal closed');
            } else {
                console.warn('Font modal instance not found');
            }
        } catch (modalError) {
            console.error('Error closing font modal:', modalError);
        }
    } catch (error) {
        console.error('Error in selectFont:', error);
        showAlert('Error selecting font: ' + error.message, 'danger');
    }
};

// Function to load template into label form
window.loadTemplate = function(config) {
    console.log('loadTemplate called with config:', config);
    try {
        var form = document.getElementById('labelForm');
        if (!form) {
            console.error('labelForm not found');
            showAlert('Error: Label form not found', 'danger');
            return;
        }

        // Reset form to clear existing values
        form.reset();

        // Populate form fields
        for (var key in config) {
            var element = form.elements[key];
            if (!element) {
                // Handle renamed length_mm
                if (key === 'length_mm') {
                    element = form.elements['length'];
                }
            }
            if (element) {
                if (element.type === 'checkbox') {
                    element.checked = config[key] === 'on' || config[key] === true;
                } else if (element.type === 'radio') {
                    var radio = form.querySelector(`input[name="${key}"][value="${config[key]}"]`);
                    if (radio) {
                        radio.checked = true;
                    }
                } else if (element.type === 'select-one') {
                    element.value = config[key];
                } else {
                    element.value = config[key];
                }
            }
        }

        // Update font-name spans for face1, face2, face3
        ['1', '2', '3'].forEach(num => {
            var face = config[`face${num}`];
            if (face) {
                var fontElement = document.querySelector(`.font-name[data-textarea="${num}"]`);
                if (fontElement) {
                    fontElement.textContent = face;
                    fontElement.style.fontFamily = face;
                }
            }
        });

        // Close the load template modal
        bootstrap.Modal.getInstance(document.getElementById('loadTemplateModal')).hide();
        showAlert('Template loaded successfully', 'success');
    } catch (error) {
        console.error('Error loading template:', error);
        showAlert('Error loading template: ' + error.message, 'danger');
    }
};

// Function to refresh the template grid
async function refreshTemplateGrid() {
    console.log('refreshTemplateGrid called');
    try {
        // Add cache-busting parameter
        const response = await fetch(`/get_templates?t=${new Date().getTime()}`);
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
        }
        const data = await response.json();
        console.log('Templates fetched:', data.templates);

        const templateGrid = document.getElementById('templateGrid');
        if (!templateGrid) {
            console.error('templateGrid element not found');
            showAlert('Error: Template grid element not found', 'danger');
            return;
        }

        // Clear the grid
        templateGrid.innerHTML = '';
        console.log('Template grid cleared');

        if (data.templates.length === 0) {
            templateGrid.innerHTML = '<p>No templates found.</p>';
            console.log('No templates found, displayed message');
            return;
        }

        // Render templates
        data.templates.forEach(template => {
            console.log('Rendering template:', template.name);
            const div = document.createElement('div');
            div.className = 'template-item';
            div.innerHTML = `
                <img src="${template.preview_image}" alt="${template.name}" title="${template.name}">
                <button class="delete-btn" title="Delete Template"><i class="bi bi-trash"></i></button>
                <p>${template.name}</p>
            `;
            // Load template on image click
            div.querySelector('img').addEventListener('click', () => {
                console.log('Image clicked for template:', template.name);
                window.loadTemplate(template.config);
            });
            // Delete template on button click
            div.querySelector('.delete-btn').addEventListener('click', (event) => {
                console.log('Delete button clicked for template:', template.name);
                event.stopPropagation(); // Prevent triggering image click
                window.deleteTemplate(template.name);
            });
            templateGrid.appendChild(div);
        });
        console.log('Template grid rendering complete, items added:', data.templates.length);
    } catch (error) {
        console.error('Error in refreshTemplateGrid:', error);
        showAlert('Error loading templates: ' + error.message, 'danger');
        document.getElementById('templateGrid').innerHTML = '<p>Error loading templates.</p>';
    }
}

// Function to delete a template
async function deleteTemplate(templateName) {
    console.log('deleteTemplate called for:', templateName);
    if (!confirm(`Are you sure you want to delete the template "${templateName}"? This cannot be undone.`)) {
        console.log('Deletion canceled for:', templateName);
        return;
    }
    try {
        // Temporarily remove the template item for immediate feedback
        const templateItems = document.querySelectorAll(`.template-item p`);
        templateItems.forEach(item => {
            if (item.textContent === templateName) {
                item.parentElement.remove();
                console.log('Removed template item from DOM:', templateName);
            }
        });

        const formData = new FormData();
        formData.append('template_name', templateName);
        const response = await fetch('/delete_template', {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.message);
        }
        const data = await response.json();
        console.log('Delete response:', data);

        showAlert(data.message, 'success');
        console.log('Success alert triggered for deletion:', templateName);

        // Refresh the template grid
        await refreshTemplateGrid();
        console.log('Grid refresh triggered after deletion');
    } catch (error) {
        console.error('Error in deleteTemplate:', error);
        showAlert('Error: ' + error.message, 'danger');
        // Re-render grid to ensure consistency
        await refreshTemplateGrid();
    }
}

// Function to show alerts
function showAlert(message, type) {
    console.log(`Attempting to show alert: ${message} (type: ${type})`);
    try {
        var alertContainer = document.getElementById('saveTemplateAlerts');
        if (!alertContainer) {
            console.error('Alert container not found (#saveTemplateAlerts)');
            alert('Error: Alert container not found - ' + message);
            return;
        }
        console.log('Alert container found:', alertContainer);
        var alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        alertContainer.appendChild(alertDiv);
        console.log('Alert appended to container:', alertDiv);
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.classList.remove('show');
                alertDiv.classList.add('fade');
                setTimeout(() => {
                    if (alertDiv.parentNode) {
                        alertDiv.remove();
                        console.log('Alert removed after timeout');
                    }
                }, 150);
            }
        }, 5000);
    } catch (error) {
        console.error('Error in showAlert:', error);
        alert('Failed to show alert: ' + message);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM content loaded');

    // Printer status check
    function checkPrinterStatus() {
        console.log('Checking printer status');
        fetch('/printer_status')
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                const statusElement = document.getElementById('printerStatus');
                if (data.online) {
                    statusElement.textContent = 'Printer: Online';
                    statusElement.classList.remove('offline');
                    statusElement.classList.add('online');
                } else {
                    statusElement.textContent = 'Printer: Offline';
                    statusElement.classList.remove('online');
                    statusElement.classList.add('offline');
                }
                console.log('Printer status updated:', data.online ? 'Online' : 'Offline');
            })
            .catch(error => {
                if (error.name === 'AbortError') {
                    console.log('Printer status check aborted');
                } else {
                    console.error('Error checking printer status:', error);
                    const statusElement = document.getElementById('printerStatus');
                    statusElement.textContent = 'Printer: Error';
                    statusElement.classList.remove('online');
                    statusElement.classList.add('offline');
                }
            });
    }

    // Initial check and periodic updates
    checkPrinterStatus();
    setInterval(checkPrinterStatus, 5000);

    // Font selection setup
    window.currentTextarea = null;
    document.querySelectorAll('.font-name').forEach(function(element) {
        element.addEventListener('click', function() {
            window.currentTextarea = this.getAttribute('data-textarea');
            console.log('Font name clicked, textarea:', window.currentTextarea);
        });
    });

    // Save template form submission with AJAX
    document.getElementById('saveTemplateForm')?.addEventListener('submit', async function(event) {
        event.preventDefault(); // Prevent default form submission
        console.log('Submitting saveTemplateForm');
        try {
            var templateName = document.getElementById('templateName').value;
            if (!templateName.trim()) {
                showAlert('Please enter a template name', 'danger');
                console.log('Empty template name, submission aborted');
                return;
            }

            var formData = new FormData(this);
            const response = await fetch('/save_template', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.message);
            }
            const data = await response.json();
            console.log('Save template response:', data);

            showAlert(data.message, 'success');
            // Close the modal on success
            bootstrap.Modal.getInstance(document.getElementById('saveTemplateModal')).hide();
            console.log('Save template modal closed');
        } catch (error) {
            console.error('Error submitting saveTemplateForm:', error);
            showAlert('Error saving template: ' + error.message, 'danger');
        }
    });

    // Ensure Save Template modal appears above Print Preview modal
    var saveTemplateModal = document.getElementById('saveTemplateModal');
    saveTemplateModal.addEventListener('show.bs.modal', function () {
        // Set z-index for modal and backdrop
        this.style.zIndex = 1060;
        var backdrop = document.querySelector('.modal-backdrop.show');
        if (backdrop) {
            backdrop.style.zIndex = 1055;
        }
        console.log('Save template modal shown, z-index set');
    });
    saveTemplateModal.addEventListener('hidden.bs.modal', function () {
        // Reset z-index when modal is hidden
        this.style.zIndex = '';
        var backdrop = document.querySelector('.modal-backdrop.show');
        if (backdrop) {
            backdrop.style.zIndex = '';
        }
        console.log('Save template modal hidden, z-index reset');
    });

    // Load Template modal setup
    var loadTemplateModal = document.getElementById('loadTemplateModal');
    loadTemplateModal.addEventListener('show.bs.modal', function () {
        // Set z-index for modal and backdrop
        this.style.zIndex = 1060;
        var backdrop = document.querySelector('.modal-backdrop.show');
        if (backdrop) {
            backdrop.style.zIndex = 1055;
        }
        console.log('Load template modal shown, z-index set');

        // Refresh the template grid
        refreshTemplateGrid();
    });
    loadTemplateModal.addEventListener('hidden.bs.modal', function () {
        // Reset z-index when modal is hidden
        this.style.zIndex = '';
        var backdrop = document.querySelector('.modal-backdrop.show');
        if (backdrop) {
            backdrop.style.zIndex = '';
        }
        console.log('Load template modal hidden, z-index reset');
    });
});
