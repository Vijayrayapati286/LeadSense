import { useEffect, useState } from 'react';
import { FiZap, FiFileText } from 'react-icons/fi';
import { templateService } from '../services/services';
import { useToast } from '../hooks/useToast';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import EmailPreview from '../components/EmailPreview';
import { renderTemplate } from '../utils/helpers';

export default function TemplatesPage() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState(null);
  const toast = useToast();

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const { data } = await templateService.getPlaceholderTemplates();
      setTemplates(data);
    } catch {
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateAI = async () => {
    setAiLoading(true);
    try {
      const { data } = await templateService.generateAI({
        campaign_name: 'Sample Campaign',
        target_audience: 'B2B Decision Makers',
      });
      setAiResult(data);
      if (data.is_mock) toast.info('Using mock AI response');
      else toast.success('AI template generated');
    } catch {
      toast.error('AI generation failed');
    } finally {
      setAiLoading(false);
    }
  };

  const previewContext = {
    Name: 'John Doe',
    Company: 'Acme Corp',
    Designation: 'CEO',
    Industry: 'Technology',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Templates</h1>
        <p className="text-gray-500 mt-1">Browse and preview email templates</p>
      </div>

      {/* AI Generation */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <FiZap className="text-amber-500" /> AI Template Generator
            </h2>
            <p className="text-sm text-gray-500 mt-1">Generate a custom email template using AI</p>
          </div>
          <button onClick={handleGenerateAI} disabled={aiLoading} className="btn-primary flex items-center gap-2">
            {aiLoading ? <LoadingSpinner size="sm" /> : <FiZap size={18} />}
            Generate
          </button>
        </div>
        {aiResult && (
          <div className="mt-4 p-4 bg-gray-50 rounded-lg">
            <p className="font-medium text-sm">{aiResult.subject}</p>
            <p className="text-sm text-gray-600 mt-2 whitespace-pre-wrap">{aiResult.body}</p>
          </div>
        )}
      </div>

      {/* Placeholder Templates */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <FiFileText className="text-primary-500" /> Placeholder Templates
          </h2>
          {templates.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelected(t)}
              className={`card w-full text-left hover:shadow-md transition-shadow ${
                selected?.id === t.id ? 'ring-2 ring-primary-500' : ''
              }`}
            >
              <p className="font-medium text-gray-900">{t.name}</p>
              <p className="text-sm text-gray-500 mt-1">{t.subject}</p>
              <div className="flex flex-wrap gap-1 mt-2">
                {t.placeholders?.map((p) => (
                  <span key={p} className="text-xs bg-primary-50 text-primary-700 px-2 py-0.5 rounded">
                    {`{{${p}}}`}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>

        <div>
          {selected ? (
            <EmailPreview
              subject={renderTemplate(selected.subject, previewContext)}
              recipientName={previewContext.Name}
              body={renderTemplate(selected.body, previewContext)}
            />
          ) : (
            <div className="card flex items-center justify-center h-64 text-gray-400">
              Select a template to preview
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
