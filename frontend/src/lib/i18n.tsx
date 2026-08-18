/* Lightweight i18n: English + Amharic, extensible (add a new dict for
   Afaan Oromo, Tigrinya, Somali, ... and it appears in the switcher). */
import { createContext, useContext, useState, type ReactNode } from 'react'

const dicts: Record<string, Record<string, string>> = {
  en: {
    tagline: 'See a problem? Report it.',
    tagline2: "We'll help get it to the right people.",
    hero_sub: 'CivicLens routes citizen reports — potholes, garbage, water leaks, power cuts, network outages, school problems — to the organization responsible, with local AI doing the triage.',
    report_issue: 'Report an Issue', explore: 'Explore Reported Issues', how: 'How It Works',
    reports_submitted: 'Reports submitted', issues_resolved: 'Issues resolved',
    orgs_notified: 'Organizations connected', reports_routed: 'Reports routed',
    recent_reports: 'Recent reports', view_all: 'View all', map: 'Map', reports: 'Reports',
    home: 'Home', login: 'Sign in', logout: 'Sign out', register: 'Create account',
    settings: 'Settings', admin: 'Admin', organization: 'Organization', priority: 'Priority',
    submit_report: 'Submit report', evidence: 'Evidence', location: 'Location',
    describe: 'Describe', review: 'Review', title: 'Title', description: 'Description',
    category_opt: 'Category (optional — AI will classify it)',
    comments_opt: 'Additional comments (optional)',
    record_video: 'Record video', upload_video: 'Upload video', add_photos: 'Add photos',
    use_my_location: 'Use my location', tap_map: 'or tap the map to set the exact spot',
    severity: 'Severity', status: 'Status', privacy: 'Privacy Policy',
    ai_disclaimer: 'AI-generated assessment — human review may change this classification.',
    ai_classification: 'AI classification', confidence: 'Confidence',
    demo_badge: 'DEMO', search: 'Search reports…', all_categories: 'All categories',
    all_statuses: 'All statuses', all_severities: 'All severities', no_results: 'No reports match your filters.',
    next: 'Next', back: 'Back', heatmap: 'Heatmap', markers: 'Markers',
    reopen: 'Reopen / dispute', reopen_confirm: 'Tell us why this issue is not actually fixed.',
    resolution_evidence: 'Resolution evidence', timeline: 'Timeline', comments: 'Comments',
    add_comment: 'Add a comment…', post: 'Post', apply: 'Apply changes',
    password: 'Password', change_password: 'Change password', current_password: 'Current password',
    new_password: 'New password', logout_all: 'Sign out of all devices',
    users: 'Users', jobs: 'Background jobs', retry: 'Retry', retry_analysis: 'Re-run AI analysis',
    needs_manual_routing: 'Needs manual routing', ai_pending: 'AI analysis pending…',
    ai_failed: 'Automatic analysis failed — this report is in manual review.',
    conf_high: 'High confidence', conf_medium: 'Medium confidence — extra review advised',
    conf_low: 'Low confidence — manual classification required',
    loading: 'Loading…', error_retry: 'Something went wrong.', try_again: 'Try again',
    save: 'Save changes', cancel: 'Cancel', confirm: 'Confirm',
    forgot_password: 'Forgot password?', reset_password: 'Reset password',
  },
  am: {
    tagline: 'ችግር አይተዋል? ሪፖርት ያድርጉ።',
    tagline2: 'ወደ ትክክለኛው አካል እናደርሳለን።',
    hero_sub: 'CivicLens የዜጎችን ሪፖርቶች — የመንገድ ጉድጓድ፣ ቆሻሻ፣ የውሃ ፍሳሽ፣ የመብራት መቋረጥ፣ የኔትወርክ ችግር፣ የትምህርት ቤት ችግሮች — በአካባቢያዊ AI ተተንትነው ኃላፊነት ላለው ተቋም ይደርሳሉ።',
    report_issue: 'ችግር ሪፖርት ያድርጉ', explore: 'የተዘገቡ ችግሮችን ይመልከቱ', how: 'እንዴት ይሰራል',
    reports_submitted: 'የገቡ ሪፖርቶች', issues_resolved: 'የተፈቱ ችግሮች',
    orgs_notified: 'የተገናኙ ተቋማት', reports_routed: 'የተመሩ ሪፖርቶች',
    recent_reports: 'የቅርብ ጊዜ ሪፖርቶች', view_all: 'ሁሉንም ይመልከቱ', map: 'ካርታ', reports: 'ሪፖርቶች',
    home: 'መነሻ', login: 'ግባ', logout: 'ውጣ', register: 'መለያ ፍጠር',
    settings: 'ማስተካከያ', admin: 'አስተዳዳሪ', organization: 'ተቋም', priority: 'ቅድሚያ',
    submit_report: 'ሪፖርት አስገባ', evidence: 'ማስረጃ', location: 'አካባቢ',
    describe: 'ግለጽ', review: 'ክለሳ', title: 'ርዕስ', description: 'መግለጫ',
    category_opt: 'ምድብ (አማራጭ — AI ይመድበዋል)',
    comments_opt: 'ተጨማሪ አስተያየት (አማራጭ)',
    record_video: 'ቪዲዮ ቅረጽ', upload_video: 'ቪዲዮ ስቀል', add_photos: 'ፎቶዎች ጨምር',
    use_my_location: 'አካባቢዬን ተጠቀም', tap_map: 'ወይም ትክክለኛውን ቦታ ካርታው ላይ ንኩ',
    severity: 'ክብደት', status: 'ሁኔታ', privacy: 'የግላዊነት ፖሊሲ',
    ai_disclaimer: 'በ AI የተሰራ ግምገማ — የሰው ክለሳ ይህን ምደባ ሊቀይር ይችላል።',
    ai_classification: 'የ AI ምደባ', confidence: 'እርግጠኝነት',
    demo_badge: 'ማሳያ', search: 'ሪፖርቶችን ፈልግ…', all_categories: 'ሁሉም ምድቦች',
    all_statuses: 'ሁሉም ሁኔታዎች', all_severities: 'ሁሉም ክብደቶች', no_results: 'ከማጣሪያዎ ጋር የሚዛመድ ሪፖርት የለም።',
    next: 'ቀጣይ', back: 'ተመለስ', heatmap: 'ሙቀት ካርታ', markers: 'ምልክቶች',
    reopen: 'እንደገና ክፈት / ተቃወም', reopen_confirm: 'ችግሩ ለምን እንዳልተፈታ ይንገሩን።',
    resolution_evidence: 'የመፍትሄ ማስረጃ', timeline: 'የጊዜ መስመር', comments: 'አስተያየቶች',
    add_comment: 'አስተያየት ጨምር…', post: 'ላክ', apply: 'ለውጦችን ተግብር',
    password: 'የይለፍ ቃል', change_password: 'የይለፍ ቃል ቀይር', current_password: 'የአሁኑ የይለፍ ቃል',
    new_password: 'አዲስ የይለፍ ቃል', logout_all: 'ከሁሉም መሣሪያዎች ውጣ',
    users: 'ተጠቃሚዎች', jobs: 'የበስተጀርባ ሥራዎች', retry: 'እንደገና ሞክር', retry_analysis: 'AI ትንተና እንደገና አካሂድ',
    needs_manual_routing: 'በእጅ መመራት ያስፈልጋል', ai_pending: 'የ AI ትንተና በሂደት ላይ…',
    ai_failed: 'ራስ-ሰር ትንተና አልተሳካም — ይህ ሪፖርት በእጅ ግምገማ ላይ ነው።',
    conf_high: 'ከፍተኛ እርግጠኝነት', conf_medium: 'መካከለኛ እርግጠኝነት — ተጨማሪ ግምገማ ይመከራል',
    conf_low: 'ዝቅተኛ እርግጠኝነት — በእጅ መመደብ ያስፈልጋል',
    loading: 'በመጫን ላይ…', error_retry: 'የሆነ ችግር ተፈጥሯል።', try_again: 'እንደገና ሞክር',
    save: 'ለውጦችን አስቀምጥ', cancel: 'ሰርዝ', confirm: 'አረጋግጥ',
    forgot_password: 'የይለፍ ቃል ረሱ?', reset_password: 'የይለፍ ቃል ዳግም አስጀምር',
  },
}

export const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'am', label: 'አማርኛ' },
]

const I18nCtx = createContext<{ lang: string; setLang: (l: string) => void; t: (k: string) => string }>({
  lang: 'en', setLang: () => {}, t: k => k,
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState(() => localStorage.getItem('cl_lang') || 'en')
  const setLang = (l: string) => { localStorage.setItem('cl_lang', l); setLangState(l) }
  const t = (k: string) => dicts[lang]?.[k] ?? dicts.en[k] ?? k
  return <I18nCtx.Provider value={{ lang, setLang, t }}>{children}</I18nCtx.Provider>
}

export const useI18n = () => useContext(I18nCtx)
