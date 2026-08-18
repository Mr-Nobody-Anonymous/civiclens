/* Global setup: build test media assets with FFmpeg and seed two failure
   fixtures (a dead background job + an AI-failed report) so browser tests can
   verify failure UX without orchestrating outages mid-test. */
import { execSync } from 'child_process'
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
const __dirname = dirname(fileURLToPath(import.meta.url))

export default async function globalSetup() {
  const assets = join(__dirname, 'assets')
  mkdirSync(assets, { recursive: true })

  if (!existsSync(join(assets, 'test.mp4'))) {
    execSync(`ffmpeg -y -f lavfi -i testsrc=duration=2:size=320x240:rate=10 ` +
      `-c:v libx264 -pix_fmt yuv420p ${join(assets, 'test.mp4')}`, { stdio: 'ignore' })
  }
  if (!existsSync(join(assets, 'evidence.png'))) {
    execSync(`ffmpeg -y -f lavfi -i color=green:size=320x240:duration=1 -frames:v 1 ` +
      `${join(assets, 'evidence.png')}`, { stdio: 'ignore' })
  }
  // text file pretending to be a video (client-side rejection test)
  writeFileSync(join(assets, 'note.txt'), 'this is not a video')
  // .mp4 extension + video/mp4 MIME but garbage content (server-side rejection test)
  writeFileSync(join(assets, 'fake.mp4'), 'garbage-bytes-not-a-real-video-file-'.repeat(10))

  // Seed failure fixtures directly in the backend DB (idempotent).
  const backend = process.env.E2E_BACKEND_DIR || join(__dirname, '..', '..', 'backend')
  const py = `
from app.db import SessionLocal, Base, engine
from app.models import Job, Report, ReportAIAnalysis, ReportStatus
Base.metadata.create_all(bind=engine)
db = SessionLocal()
if not db.query(Job).filter_by(name='e2e_dead_job').first():
    db.add(Job(name='e2e_dead_job', payload='{}', status='dead', attempts=3,
               max_attempts=3, last_error='E2E fixture: simulated permanent failure'))
if not db.query(Report).filter_by(title='E2E AI-failed fixture report').first():
    r = Report(title='E2E AI-failed fixture report',
               description='Fixture report whose automatic analysis failed; used by browser tests.',
               category='Water', user_category='Water', city='Addis Ababa',
               latitude=9.03, longitude=38.74, status=ReportStatus.under_review,
               processing_state='failed', processing_error='ConnectError: AI service unreachable',
               routing_state='needs_manual_routing')
    db.add(r); db.commit()
    db.add(ReportAIAnalysis(report_id=r.id, success=False, analyzer='none',
                            model_name='unavailable', model_version='-',
                            reasoning='Analysis failed: ConnectError: AI service unreachable'))
db.commit(); db.close()
print('fixtures ok')
`
  execSync(`python3 -c "${py.replace(/"/g, '\\"')}"`, { cwd: backend, stdio: 'inherit' })
}
