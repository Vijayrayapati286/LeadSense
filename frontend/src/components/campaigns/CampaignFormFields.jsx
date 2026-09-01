import { FiCheckCircle, FiChevronDown, FiCreditCard, FiEdit3, FiHome, FiUsers } from 'react-icons/fi';
import CampaignSourcePicker from './CampaignSourcePicker';

const DEPARTMENTS = ['Sales', 'Marketing', 'Customer Success', 'Operations', 'Product', 'Engineering'];
const TARGET_AUDIENCES = [
  'B2B Decision Makers',
  'Enterprise Buyers',
  'SMB Owners',
  'Technical Leaders',
  'HR Managers',
  'C-Suite Executives',
];

const DESCRIPTION_MAX = 500;

function FieldLabel({ children, required }) {
  return (
    <label className="block text-sm font-semibold text-slate-800 mb-1.5">
      {children}
      {required ? <span className="text-primary-600 ml-0.5">*</span> : null}
    </label>
  );
}

function IconField({ icon: Icon, iconClass, iconBg, children, trailing }) {
  return (
    <div className="relative">
      <span className={`absolute left-3 top-1/2 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-md ${iconBg}`}>
        <Icon size={14} className={iconClass} />
      </span>
      {children}
      {trailing ? (
        <span className="absolute right-3 top-1/2 -translate-y-1/2">{trailing}</span>
      ) : null}
    </div>
  );
}

function getInitials(name) {
  return (name || '?')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

export default function CampaignFormFields({
  form,
  updateForm,
  isEditMode,
  campaignSource,
  onCampaignSourceChange,
  offerings,
  mailers,
  selectedOfferingId,
  selectedSmartOpsId,
  onOfferingSelect,
  onSmartOpsSelect,
  loadingSource,
  users = [],
}) {
  const selectedUser = users.find((u) => u.name === form.owner);
  const idValid = Boolean(form.campaign_id?.trim());

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {!isEditMode ? (
          <CampaignSourcePicker
            value={campaignSource}
            onChange={onCampaignSourceChange}
            offerings={offerings}
            mailers={mailers}
            selectedOfferingId={selectedOfferingId}
            selectedSmartOpsId={selectedSmartOpsId}
            onOfferingSelect={onOfferingSelect}
            onSmartOpsSelect={onSmartOpsSelect}
            loadingSource={loadingSource}
          />
        ) : null}

        <div>
          <FieldLabel required>Campaign Name</FieldLabel>
          <IconField icon={FiEdit3} iconBg="bg-violet-50" iconClass="text-violet-600">
            <input
              className="campaign-field-input pl-12"
              value={form.campaign_name}
              onChange={(e) => updateForm('campaign_name', e.target.value)}
              placeholder="Q1 Product Launch"
            />
          </IconField>
        </div>

        <div className={isEditMode ? 'md:col-span-2' : ''}>
          <FieldLabel required>Campaign ID</FieldLabel>
          <IconField
            icon={FiCreditCard}
            iconBg="bg-emerald-50"
            iconClass="text-emerald-600"
            trailing={idValid ? <FiCheckCircle size={18} className="text-emerald-500" /> : null}
          >
            <input
              className="campaign-field-input pl-12 pr-10 font-mono text-sm"
              value={form.campaign_id}
              onChange={(e) => updateForm('campaign_id', e.target.value)}
            />
          </IconField>
        </div>
      </div>

      <div>
        <FieldLabel>Campaign Description</FieldLabel>
        <div className="relative">
          <textarea
            className="campaign-field-textarea"
            rows={4}
            maxLength={DESCRIPTION_MAX}
            value={form.description}
            onChange={(e) => updateForm('description', e.target.value)}
            placeholder="Describe the campaign purpose, goals, and key messaging..."
          />
          <span className="absolute bottom-3 right-3 text-xs text-slate-400">
            {form.description.length} / {DESCRIPTION_MAX}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <FieldLabel>Owner</FieldLabel>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 text-xs font-bold text-primary-700 z-10 pointer-events-none">
              {getInitials(selectedUser?.name || form.owner)}
            </span>
            <select
              className="campaign-field-select pl-14 pr-10 appearance-none"
              value={form.owner}
              onChange={(e) => updateForm('owner', e.target.value)}
            >
              {users.length > 0 ? (
                users.map((u) => (
                  <option key={u.id} value={u.name}>
                    {u.name}
                  </option>
                ))
              ) : (
                <option value={form.owner}>{form.owner || 'Select owner'}</option>
              )}
            </select>
            <FiChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>
          {selectedUser?.email ? (
            <p className="mt-1 text-xs text-slate-500 pl-1">{selectedUser.email}</p>
          ) : null}
        </div>

        <div>
          <FieldLabel>Department</FieldLabel>
          <div className="relative">
            <IconField icon={FiHome} iconBg="bg-amber-50" iconClass="text-amber-600">
              <select
                className="campaign-field-select pl-12 pr-10 appearance-none"
                value={form.department}
                onChange={(e) => updateForm('department', e.target.value)}
              >
                {DEPARTMENTS.map((dept) => (
                  <option key={dept} value={dept}>{dept}</option>
                ))}
              </select>
            </IconField>
            <FiChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>
        </div>

        <div>
          <FieldLabel>Target Audience</FieldLabel>
          <div className="relative">
            <IconField icon={FiUsers} iconBg="bg-violet-50" iconClass="text-violet-600">
              <select
                className="campaign-field-select pl-12 pr-10 appearance-none"
                value={form.target_audience}
                onChange={(e) => updateForm('target_audience', e.target.value)}
              >
                <option value="">Select audience...</option>
                {form.target_audience && !TARGET_AUDIENCES.includes(form.target_audience) ? (
                  <option value={form.target_audience}>{form.target_audience}</option>
                ) : null}
                {TARGET_AUDIENCES.map((audience) => (
                  <option key={audience} value={audience}>{audience}</option>
                ))}
              </select>
            </IconField>
            <FiChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>
        </div>
      </div>
    </div>
  );
}
