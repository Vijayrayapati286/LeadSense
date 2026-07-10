import { renderMarkdownLite } from '../utils/helpers';

export default function EmailPreview({ subject, recipientName, body, closing, cta }) {
  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
        {/* Email client header */}
        <div className="bg-gray-100 px-4 py-3 border-b border-gray-200">
          <div className="flex items-center gap-2 mb-2">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-400" />
              <div className="w-3 h-3 rounded-full bg-amber-400" />
              <div className="w-3 h-3 rounded-full bg-green-400" />
            </div>
            <span className="text-xs text-gray-500 ml-2">Email Preview</span>
          </div>
          <div className="space-y-1 text-sm">
            <div className="flex gap-2">
              <span className="text-gray-500 w-16">To:</span>
              <span className="text-gray-900 font-medium">{recipientName}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-gray-500 w-16">Subject:</span>
              <span className="text-gray-900 font-medium">{subject}</span>
            </div>
          </div>
        </div>

        {/* Email body */}
        <div className="p-6">
          <div
            className="prose prose-sm max-w-none text-gray-700 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: renderMarkdownLite(body) }}
          />
          {closing && (
            <div
              className="mt-4 text-gray-700"
              dangerouslySetInnerHTML={{ __html: renderMarkdownLite(closing) }}
            />
          )}
          {cta && (
            <div className="mt-6">
              <span className="inline-block bg-primary-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium">
                {cta}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
