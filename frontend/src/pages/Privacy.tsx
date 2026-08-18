import { ShieldCheck } from 'lucide-react'

const SECTIONS = [
  ['What we collect', 'When you submit a report we store: the issue title and description, the location you choose to share, and any video or photo evidence you upload. If you create an account we also store your name, email and city. Anonymous reporting is supported.'],
  ['Location permission', 'We only access your device location when you tap "Use my location", and only after your browser asks for permission. You can always pick the location manually on the map instead. Public map pins are slightly rounded to protect precise addresses.'],
  ['How videos are used', 'Uploaded videos and photos are used for two purposes only: (1) automated analysis by our locally-hosted AI to classify the issue, and (2) review by moderators and the responsible organization to fix the problem. Files are stored on secure servers and are streamed through access-controlled endpoints — storage is never exposed directly.'],
  ['AI analysis', 'Our AI runs locally/on-premise. It classifies the issue type, estimates severity and recommends a responsible organization. AI output is a recommendation with a confidence score — human reviewers can and do correct it. We do not use AI to automatically identify people in your videos.'],
  ['What is public', 'The public sees: issue title, description, category, severity, status, approximate location and evidence media. The public never sees your name, email, phone number, or any account details.'],
  ['Who can see more', 'Moderators, administrators and the assigned organization can see reporter contact details when needed to resolve an issue. All administrative actions are recorded in an audit log.'],
  ['Your rights', 'You can delete your account at any time from Settings. Deletion removes your personal data and anonymises your reports. You may also request removal of a specific report or video by contacting the platform team.'],
  ['Security', 'Passwords are stored using strong one-way hashing (PBKDF2). Sessions use secure HTTP-only cookies. Uploads are validated by type, size and content signature. Access to admin features is role-based and rate limits protect against abuse.'],
  ['Changes', 'If this policy changes we will publish the new version on this page with the date of update.'],
]

export default function Privacy() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <div className="flex items-center gap-3">
        <span className="grid size-12 place-items-center rounded-2xl bg-brand-600/10 text-brand-700 dark:text-brand-300"><ShieldCheck className="size-6" /></span>
        <div>
          <h1 className="text-2xl font-extrabold md:text-3xl">Privacy Policy</h1>
          <p className="text-sm text-ink-500 dark:text-ink-400">CivicLens Ethiopia · Last updated {new Date().toLocaleDateString()}</p>
        </div>
      </div>
      <p className="mt-6 text-ink-600 dark:text-ink-300">
        CivicLens Ethiopia exists to help citizens improve their cities — not to collect data about them.
        This page explains, in plain language, what we store and why.
      </p>
      <div className="mt-8 space-y-6">
        {SECTIONS.map(([h, b], i) => (
          <section key={i} className="card p-6">
            <h2 className="font-bold">{i + 1}. {h}</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-600 dark:text-ink-300">{b}</p>
          </section>
        ))}
      </div>
    </div>
  )
}
