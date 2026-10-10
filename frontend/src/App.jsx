import React, { useState, useEffect, useRef } from 'react';
import {
  Award,
  CheckCircle2,
  AlertCircle,
  Download,
  Eye,
  Plus,
  Trash2,
  RefreshCw,
  Upload,
  FileSpreadsheet,
  Layers,
  Sparkles,
  ShieldAlert,
  X,
  ExternalLink,
  Clock
} from 'lucide-react';
import './App.css';

const API_BASE = ''; // Uses Vite proxy in development or relative path in production

const DEFAULT_SAMPLES = [
  { name: 'Elena Rostova', email: 'elena.rostova@example.com', course_name: 'Advanced Distributed Systems', issue_date: 'October 10, 2026' },
  { name: 'Marcus Vance', email: 'marcus.vance@example.com', course_name: 'Advanced Distributed Systems', issue_date: 'October 10, 2026' },
  { name: 'Amara Okafor', email: 'amara.okafor@example.com', course_name: 'Advanced Distributed Systems', issue_date: 'October 10, 2026' },
];

const FAULT_ISOLATION_SAMPLES = [
  { name: 'Devon Miles (Valid)', email: 'devon.miles@example.com', course_name: 'Cloud Architecture & Kubernetes', issue_date: 'October 10, 2026' },
  { name: 'Fault Simulated User', email: 'simulate.fail@demo.com', course_name: 'Cloud Architecture & Kubernetes', issue_date: 'October 10, 2026' },
  { name: 'Nadia Kasim (Valid)', email: 'nadia.kasim@example.com', course_name: 'Cloud Architecture & Kubernetes', issue_date: 'October 10, 2026' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('manual'); // 'manual' | 'csv'
  const [apiOnline, setApiOnline] = useState(false);
  const [jobTitle, setJobTitle] = useState('Advanced Systems Engineering Cohort');
  const [recipients, setRecipients] = useState(DEFAULT_SAMPLES);
  const [simulateEmails, setSimulateEmails] = useState([]);
  
  // Active Job & Polling states
  const [currentJob, setCurrentJob] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [jobsHistory, setJobsHistory] = useState([]);
  const [toastMessage, setToastMessage] = useState(null);

  // Modal Preview state
  const [previewCert, setPreviewCert] = useState(null);

  // File upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  // Check backend health on mount
  useEffect(() => {
    checkHealth();
    fetchHistory();
  }, []);

  // Live polling effect when job is in progress
  useEffect(() => {
    if (!currentJob) return;
    const isRunning = currentJob.status === 'PENDING' || currentJob.status === 'PROCESSING';
    if (!isRunning) return;

    const interval = setInterval(() => {
      pollJobStatus(currentJob.id);
    }, 900);

    return () => clearInterval(interval);
  }, [currentJob?.id, currentJob?.status]);

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (res.ok) setApiOnline(true);
      else setApiOnline(false);
    } catch {
      setApiOnline(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs?limit=10`);
      if (res.ok) {
        const data = await res.json();
        setJobsHistory(data);
      }
    } catch (err) {
      console.error('Failed to fetch job history:', err);
    }
  };

  const pollJobStatus = async (jobId) => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
      if (res.ok) {
        const data = await res.json();
        setCurrentJob(data);
        if (data.status === 'COMPLETED' || data.status === 'PARTIAL_FAILURE' || data.status === 'FAILED') {
          fetchHistory(); // Refresh recent list
        }
      }
    } catch (err) {
      console.error('Error polling job status:', err);
    }
  };

  // Recipient row management
  const handleRecipientChange = (index, field, value) => {
    const updated = [...recipients];
    updated[index][field] = value;
    setRecipients(updated);
  };

  const handleAddRecipient = () => {
    setRecipients([
      ...recipients,
      { name: '', email: '', course_name: recipients[0]?.course_name || 'Full-Stack Engineering', issue_date: 'October 10, 2026' }
    ]);
  };

  const handleRemoveRecipient = (index) => {
    if (recipients.length <= 1) {
      showToast('At least one recipient is required.', 'error');
      return;
    }
    setRecipients(recipients.filter((_, i) => i !== index));
  };

  const handleLoadSamples = () => {
    setRecipients(DEFAULT_SAMPLES);
    setSimulateEmails([]);
    setJobTitle('Advanced Systems Engineering Cohort');
    showToast('Loaded standard recipient cohort.', 'info');
  };

  const handleLoadFaultDemo = () => {
    setRecipients(FAULT_ISOLATION_SAMPLES);
    setSimulateEmails(['simulate.fail@demo.com']);
    setJobTitle('Fault Tolerance & Isolation Demo');
    showToast('Loaded test batch containing 1 intentional failure to verify fault tolerance.', 'info');
  };

  const showToast = (msg, type = 'info') => {
    setToastMessage({ msg, type });
    setTimeout(() => setToastMessage(null), 5000);
  };

  // Submit Bulk Job (Manual)
  const handleSubmitJob = async () => {
    // Client-side quick check
    for (let i = 0; i < recipients.length; i++) {
      const r = recipients[i];
      if (!r.name.trim()) {
        showToast(`Recipient #${i + 1} has an empty name.`, 'error');
        return;
      }
      if (!r.email.trim() || !r.email.includes('@')) {
        showToast(`Recipient #${i + 1} has an invalid email address.`, 'error');
        return;
      }
      if (!r.course_name.trim()) {
        showToast(`Recipient #${i + 1} has an empty course title.`, 'error');
        return;
      }
    }

    setIsSubmitting(true);
    try {
      const payload = {
        title: jobTitle || 'Bulk Certificate Generation',
        recipients: recipients,
        simulate_failure_emails: simulateEmails.length > 0 ? simulateEmails : undefined
      };

      const res = await fetch(`${API_BASE}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to submit bulk job');
      }

      const jobData = await res.json();
      setCurrentJob(jobData);
      showToast(`Job submitted! Asynchronous generation initiated (ID: ${jobData.id.slice(0, 8)}).`, 'info');
      fetchHistory();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle CSV Upload
  const handleCsvUpload = async () => {
    if (!selectedFile) {
      showToast('Please select a CSV file first.', 'error');
      return;
    }

    setIsSubmitting(true);
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('title', jobTitle || 'CSV Bulk Certificate Generation');

    try {
      const res = await fetch(`${API_BASE}/api/jobs/upload-csv`, {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errData = await res.json();
        const msg = typeof errData.detail === 'object' ? JSON.stringify(errData.detail) : errData.detail;
        throw new Error(msg || 'Failed to process CSV');
      }

      const jobData = await res.json();
      setCurrentJob(jobData);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      showToast('CSV uploaded successfully! Processing certificates in background.', 'info');
      fetchHistory();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const downloadSampleCsv = () => {
    const csvContent =
      'name,email,course_name,issue_date\n' +
      'Alexander Hamilton,alex@example.com,Constitutional Economics,October 10, 2026\n' +
      'Thomas Jefferson,thomas@example.com,Political Philosophy,October 10, 2026\n' +
      'James Madison,james@example.com,Federal Jurisprudence,October 10, 2026\n';

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'sample_recipients.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const getStatusBadgeClass = (status) => {
    return `badge-status ${status}`;
  };

  return (
    <div className="app-container">
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`toast-msg ${toastMessage.type}`}>
          {toastMessage.type === 'error' ? <AlertCircle size={20} /> : <Sparkles size={20} />}
          <span>{toastMessage.msg}</span>
        </div>
      )}

      {/* Header */}
      <header className="app-header glass-panel">
        <div className="brand-wrapper">
          <div className="brand-icon">
            <Award size={30} />
          </div>
          <div>
            <h1 className="brand-title">CertiFlow</h1>
            <p className="brand-subtitle">Enterprise Bulk Certificate Generator & Issuance Engine</p>
          </div>
        </div>

        <div className="header-meta">
          <div className={`status-pill ${apiOnline ? 'online' : ''}`}>
            <span className="status-dot"></span>
            <span>{apiOnline ? 'FastAPI Backend Live' : 'Connecting to API...'}</span>
          </div>
        </div>
      </header>

      {/* Input Mode Selector */}
      <div className="tabs-nav">
        <button
          className={`tab-btn ${activeTab === 'manual' ? 'active' : ''}`}
          onClick={() => setActiveTab('manual')}
        >
          <Layers size={17} />
          Interactive Grid Builder
        </button>
        <button
          className={`tab-btn ${activeTab === 'csv' ? 'active' : ''}`}
          onClick={() => setActiveTab('csv')}
        >
          <FileSpreadsheet size={17} />
          CSV File Upload
        </button>
      </div>

      {/* Creation Panel */}
      <section className="creation-panel glass-panel">
        <div className="panel-header">
          <h2 className="panel-title">
            {activeTab === 'manual' ? 'Recipient Batch Definition' : 'Bulk CSV Ingestion'}
          </h2>

          <div className="quick-actions">
            {activeTab === 'manual' && (
              <>
                <button className="action-btn-sm" onClick={handleLoadSamples}>
                  <Sparkles size={15} />
                  Load Standard Cohort
                </button>
                <button className="action-btn-sm fault-demo" onClick={handleLoadFaultDemo}>
                  <ShieldAlert size={15} />
                  Simulate Fault Tolerance Test
                </button>
              </>
            )}
            {activeTab === 'csv' && (
              <button className="action-btn-sm" onClick={downloadSampleCsv}>
                <Download size={15} />
                Download Sample CSV
              </button>
            )}
          </div>
        </div>

        {activeTab === 'manual' ? (
          <>
            <div className="recipients-table-wrapper">
              <table className="editor-table">
                <thead>
                  <tr>
                    <th style={{ width: '40px' }}>#</th>
                    <th>Full Name</th>
                    <th>Email Address</th>
                    <th>Course / Award Title</th>
                    <th>Issue Date</th>
                    <th style={{ width: '60px' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {recipients.map((r, idx) => {
                    const isSimulatedFail = simulateEmails.includes(r.email);
                    return (
                      <tr key={idx}>
                        <td style={{ color: 'var(--text-dim)', textAlign: 'center' }}>{idx + 1}</td>
                        <td>
                          <input
                            type="text"
                            className="editor-input"
                            placeholder="e.g. Marie Curie"
                            value={r.name}
                            onChange={(e) => handleRecipientChange(idx, 'name', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="email"
                            className={`editor-input ${isSimulatedFail ? 'sim-fail-input' : ''}`}
                            placeholder="e.g. marie@domain.com"
                            value={r.email}
                            onChange={(e) => handleRecipientChange(idx, 'email', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="editor-input"
                            placeholder="Course Name"
                            value={r.course_name}
                            onChange={(e) => handleRecipientChange(idx, 'course_name', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            className="editor-input"
                            placeholder="October 10, 2026"
                            value={r.issue_date}
                            onChange={(e) => handleRecipientChange(idx, 'issue_date', e.target.value)}
                          />
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <button
                            className="icon-btn-danger"
                            title="Remove recipient"
                            onClick={() => handleRemoveRecipient(idx)}
                          >
                            <Trash2 size={16} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <button className="action-btn-sm" onClick={handleAddRecipient} style={{ marginBottom: '16px' }}>
              <Plus size={16} />
              Add Another Recipient
            </button>
          </>
        ) : (
          <div className="csv-upload-section">
            <div
              className="csv-dropzone"
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
            >
              <Upload className="csv-icon" />
              <h3>{selectedFile ? selectedFile.name : 'Click or Drag CSV File Here'}</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '6px' }}>
                Must contain columns: <code>name, email, course_name, issue_date</code>
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                style={{ display: 'none' }}
                onChange={(e) => setSelectedFile(e.target.files[0])}
              />
            </div>
          </div>
        )}

        <div className="submit-bar">
          <input
            type="text"
            className="job-title-input"
            placeholder="Job Title (e.g., Q4 Engineering Graduates)"
            value={jobTitle}
            onChange={(e) => setJobTitle(e.target.value)}
          />

          <button
            className="btn-primary"
            disabled={isSubmitting}
            onClick={activeTab === 'manual' ? handleSubmitJob : handleCsvUpload}
          >
            {isSubmitting ? (
              <>
                <RefreshCw size={18} className="animate-spin" />
                Submitting Batch...
              </>
            ) : (
              <>
                <Award size={18} />
                Generate {activeTab === 'manual' ? `${recipients.length} Certificates in Bulk` : 'from CSV'}
              </>
            )}
          </button>
        </div>
      </section>

      {/* Active Job Progress & Deliverables Dashboard */}
      {currentJob && (
        <section className="job-monitor-panel glass-panel">
          <div className="monitor-top">
            <div>
              <h2 className="monitor-job-title">
                {currentJob.title}
                <span className={getStatusBadgeClass(currentJob.status)}>
                  {currentJob.status === 'COMPLETED' && <CheckCircle2 size={14} />}
                  {currentJob.status === 'PARTIAL_FAILURE' && <AlertCircle size={14} />}
                  {currentJob.status === 'FAILED' && <AlertCircle size={14} />}
                  {currentJob.status === 'PROCESSING' && <RefreshCw size={14} className="animate-spin" />}
                  {currentJob.status}
                </span>
              </h2>
              <span className="monitor-meta-id">Job ID: {currentJob.id}</span>
            </div>

            <button
              className="action-btn-sm"
              onClick={() => pollJobStatus(currentJob.id)}
              title="Refresh status"
            >
              <RefreshCw size={14} />
              Refresh Status
            </button>
          </div>

          {/* Animated Progress Bar */}
          <div className="progress-card">
            <div className="progress-header">
              <span>Overall Progress</span>
              <span>{currentJob.progress_percentage}% ({currentJob.processed_count} / {currentJob.total_count})</span>
            </div>
            <div className="progress-track">
              <div
                className={`progress-fill ${
                  currentJob.status === 'PROCESSING' ? 'animated-stripes' : ''
                }`}
                style={{ width: `${Math.max(currentJob.progress_percentage, 4)}%` }}
              ></div>
            </div>
          </div>

          {/* Metric Stats Cards */}
          <div className="stats-grid">
            <div className="stat-box primary">
              <span className="stat-label">Total Recipients</span>
              <span className="stat-value">{currentJob.total_count}</span>
            </div>
            <div className="stat-box success">
              <span className="stat-label">Generated Successfully</span>
              <span className="stat-value">{currentJob.success_count}</span>
            </div>
            <div className="stat-box danger">
              <span className="stat-label">Isolated Failures</span>
              <span className="stat-value">{currentJob.failed_count}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Execution Status</span>
              <span className="stat-value" style={{ fontSize: '18px', textTransform: 'capitalize' }}>
                {currentJob.status.toLowerCase().replace('_', ' ')}
              </span>
            </div>
          </div>

          {/* Bulk ZIP Download Banner */}
          {currentJob.zip_download_url && currentJob.success_count > 0 && (
            <div className="zip-banner">
              <div className="zip-info">
                <div className="zip-icon-wrapper">
                  <Download size={24} />
                </div>
                <div>
                  <h4 style={{ fontWeight: 700, color: '#065f46' }}>Bulk ZIP Archive Ready</h4>
                  <p style={{ fontSize: '13px', color: '#047857' }}>
                    Download all {currentJob.success_count} generated certificates bundled in a single ZIP package.
                  </p>
                </div>
              </div>

              <a
                href={`${API_BASE}${currentJob.zip_download_url}`}
                className="btn-download-zip"
                download
              >
                <Download size={16} />
                Download All ({currentJob.success_count} Certificates) as ZIP
              </a>
            </div>
          )}

          {/* Individual Certificates Deliverables Table */}
          <div className="results-table-container">
            <table className="results-table">
              <thead>
                <tr>
                  <th>Recipient</th>
                  <th>Course / Program</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>File / Diagnostic</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {currentJob.certificates.map((cert) => (
                  <tr key={cert.id}>
                    <td>
                      <div className="recipient-cell">
                        <span className="recipient-name">{cert.recipient_name}</span>
                        <span className="recipient-email">{cert.recipient_email}</span>
                      </div>
                    </td>
                    <td style={{ color: '#334155', fontWeight: 500 }}>{cert.course_name}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{cert.issue_date}</td>
                    <td>
                      <span className={getStatusBadgeClass(cert.status)}>
                        {cert.status === 'SUCCESS' && <CheckCircle2 size={12} />}
                        {cert.status === 'FAILED' && <AlertCircle size={12} />}
                        {cert.status}
                      </span>
                    </td>
                    <td>
                      {cert.status === 'SUCCESS' && (
                        <span style={{ fontSize: '13px', color: '#94a3b8', fontFamily: 'monospace' }}>
                          {cert.file_name}
                        </span>
                      )}
                      {cert.status === 'FAILED' && (
                        <div className="error-pill" title={cert.error_message}>
                          <ShieldAlert size={14} />
                          <span>{cert.error_message || 'Rendering error isolated'}</span>
                        </div>
                      )}
                      {cert.status === 'PENDING' && (
                        <span style={{ fontSize: '13px', color: 'var(--text-dim)' }}>Queued in worker...</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div className="table-actions" style={{ justifyContent: 'flex-end' }}>
                        {cert.preview_url && (
                          <button
                            className="btn-action-icon"
                            onClick={() => setPreviewCert(cert)}
                            title="Inspect certificate image"
                          >
                            <Eye size={14} />
                            Preview
                          </button>
                        )}
                        {cert.download_url && (
                          <a
                            href={`${API_BASE}${cert.download_url}`}
                            className="btn-action-icon primary"
                            download
                            title="Download certificate PNG"
                          >
                            <Download size={14} />
                            PNG
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Historical Generation Jobs Section */}
      {jobsHistory.length > 0 && (
        <section className="history-section">
          <h3 className="panel-title" style={{ marginBottom: '16px' }}>
            <Clock size={20} />
            Previous Generation Jobs
          </h3>
          <div className="history-grid">
            {jobsHistory.map((j) => (
              <div
                key={j.id}
                className={`glass-card history-card ${currentJob?.id === j.id ? 'active-card' : ''}`}
                onClick={() => pollJobStatus(j.id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span className={getStatusBadgeClass(j.status)}>{j.status}</span>
                  <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                    {j.total_count} certs
                  </span>
                </div>
                <h4 style={{ fontWeight: 600, color: '#0f172a', marginBottom: '4px', fontSize: '15px' }}>
                  {j.title}
                </h4>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Success: {j.success_count} | Failed: {j.failed_count}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Modal Certificate Preview */}
      {previewCert && (
        <div className="modal-overlay" onClick={() => setPreviewCert(null)}>
          <div className="modal-content glass-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 className="modal-title">Certificate Preview</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                  {previewCert.recipient_name} — {previewCert.course_name}
                </p>
              </div>
              <button
                className="icon-btn-danger"
                style={{ background: 'transparent', color: '#64748b', border: 'none' }}
                onClick={() => setPreviewCert(null)}
              >
                <X size={20} />
              </button>
            </div>

            <img
              src={`${API_BASE}${previewCert.preview_url}`}
              alt={`Certificate for ${previewCert.recipient_name}`}
              className="modal-preview-img"
            />

            <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <a
                href={`${API_BASE}${previewCert.download_url}`}
                className="btn-primary"
                download
              >
                <Download size={16} />
                Download High-Res PNG
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

