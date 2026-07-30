import { FiAlertTriangle } from 'react-icons/fi';
import Modal from './Modal';

/**
 * Shown when a prospect-list upload is rejected for missing required
 * columns (Name / Email ID) — lists exactly which ones, per column, rather
 * than a single generic error string.
 */
export default function UploadErrorModal({ isOpen, onClose, missingColumns = [] }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Upload Failed" size="sm">
      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <FiAlertTriangle className="text-red-500 mt-0.5 flex-shrink-0" size={22} />
          <div>
            <p className="font-medium text-gray-900">
              Required column{missingColumns.length > 1 ? 's' : ''} missing:
            </p>
            <ul className="mt-2 space-y-1.5">
              {missingColumns.map((col) => (
                <li
                  key={col}
                  className="text-red-700 bg-red-50 border border-red-100 rounded-md px-3 py-1.5 text-sm font-medium"
                >
                  {col}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="text-sm text-gray-500">
          Please upload a file containing all mandatory columns, then try again.
        </p>
        <div className="flex justify-end">
          <button onClick={onClose} className="btn-primary">Got it</button>
        </div>
      </div>
    </Modal>
  );
}
