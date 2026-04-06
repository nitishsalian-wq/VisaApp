/**
 * VisaDesk Application JavaScript
 */

// Initialize tooltips and popovers
document.addEventListener('DOMContentLoaded', function() {
    // Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // File upload area drag-and-drop
    const uploadArea = document.getElementById('uploadArea');
    if (uploadArea) {
        uploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.remove('dragover');

            const files = e.dataTransfer.files;
            const fileInput = document.getElementById('fileInput');
            if (fileInput && files.length > 0) {
                fileInput.files = files;
                // Trigger change event
                fileInput.dispatchEvent(new Event('change'));
            }
        });

        // Click to upload
        uploadArea.addEventListener('click', function() {
            const fileInput = document.getElementById('fileInput');
            if (fileInput) {
                fileInput.click();
            }
        });
    }
});

/**
 * Format date string to readable format
 */
function formatDate(dateString) {
    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

/**
 * Show alert message
 */
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    const container = document.querySelector('.main-container') || document.body;
    container.insertBefore(alertDiv, container.firstChild);

    // Auto-dismiss after 5 seconds
    setTimeout(function() {
        const alert = bootstrap.Alert.getOrCreateInstance(alertDiv);
        alert.close();
    }, 5000);
}

/**
 * Load and render status distribution chart
 */
function loadStatusDistributionChart() {
    const ctx = document.getElementById('statusChart');
    if (!ctx) return;

    fetch('/dashboard/data/status-distribution')
        .then(response => response.json())
        .then(data => {
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.data,
                        backgroundColor: [
                            '#95a5a6',  // draft
                            '#3498db',  // documents_uploaded
                            '#27ae60',  // qc_passed
                            '#e74c3c',  // qc_failed
                            '#f39c12',  // submitted
                            '#27ae60',  // approved
                            '#e74c3c'   // rejected
                        ],
                        borderColor: 'white',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        })
        .catch(error => console.error('Error loading chart:', error));
}

/**
 * Load and render weekly volume chart
 */
function loadWeeklyVolumeChart() {
    const ctx = document.getElementById('weeklyChart');
    if (!ctx) return;

    fetch('/dashboard/data/weekly-volume')
        .then(response => response.json())
        .then(data => {
            const weeks = data.map(d => d.week);
            const applicants = data.map(d => d.applicants);
            const qcRuns = data.map(d => d.qc_runs);

            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: weeks,
                    datasets: [
                        {
                            label: 'New Applicants',
                            data: applicants,
                            backgroundColor: '#3498db'
                        },
                        {
                            label: 'QC Runs',
                            data: qcRuns,
                            backgroundColor: '#27ae60'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        })
        .catch(error => console.error('Error loading chart:', error));
}

/**
 * Load QC history for an applicant
 */
function loadQCHistory(applicantId) {
    fetch(`/qc/history/${applicantId}`)
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('qcHistoryContainer');
            if (!container) return;

            if (data.length === 0) {
                container.innerHTML = '<p class="text-muted">No QC checks have been run yet.</p>';
                return;
            }

            let html = '<div class="timeline">';
            data.forEach(report => {
                const statusClass = `badge bg-${report.overall_status === 'pass' ? 'success' : report.overall_status === 'fail' ? 'danger' : 'warning'}`;
                html += `
                    <div class="timeline-item mb-3">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <h6 class="mb-1">QC Report #${report.id}</h6>
                                <p class="text-muted small mb-2">${formatDate(report.run_at)}</p>
                                <p class="small">
                                    <span class="${statusClass}">${report.overall_status.toUpperCase()}</span>
                                </p>
                                <p class="small">
                                    <strong>Passed:</strong> ${report.passed_checks}/${report.total_checks} checks
                                </p>
                            </div>
                            <a href="/qc/report/${report.id}" class="btn btn-sm btn-outline-primary">View Report</a>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            container.innerHTML = html;
        })
        .catch(error => console.error('Error loading QC history:', error));
}

/**
 * Initialize page based on loaded scripts
 */
document.addEventListener('DOMContentLoaded', function() {
    // Load charts if Chart.js is available
    if (typeof Chart !== 'undefined') {
        loadStatusDistributionChart();
        loadWeeklyVolumeChart();
    }

    // Load QC history if on applicant detail page
    const applicantIdEl = document.getElementById('applicantId');
    if (applicantIdEl) {
        loadQCHistory(applicantIdEl.value);
    }
});
