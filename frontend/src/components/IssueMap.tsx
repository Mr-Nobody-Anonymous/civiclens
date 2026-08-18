/* Reusable Leaflet map: severity-coloured markers, clustering, heatmap, click-to-pick. */
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet.markercluster'
import 'leaflet.heat'
import { SEVERITY } from '../lib/types'

export interface MapPoint {
  id: string; lat: number; lng: number; severity?: number | null
  title?: string; category?: string; status?: string; code?: string
}

interface Props {
  points?: MapPoint[]
  center?: [number, number]
  zoom?: number
  heatmap?: boolean
  cluster?: boolean
  onPick?: (lat: number, lng: number) => void
  picked?: [number, number] | null
  onMarkerClick?: (id: string) => void
  className?: string
}

export default function IssueMap({ points = [], center = [9.0108, 38.7613], zoom = 12,
  heatmap = false, cluster = true, onPick, picked, onMarkerClick, className = 'h-96' }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.Layer | null>(null)
  const pickRef = useRef<L.Marker | null>(null)
  const cbRef = useRef({ onPick, onMarkerClick })
  cbRef.current = { onPick, onMarkerClick }

  useEffect(() => {
    if (!el.current || mapRef.current) return
    const map = L.map(el.current, { zoomControl: true, attributionControl: true }).setView(center, zoom)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '© OpenStreetMap contributors',
    }).addTo(map)
    map.on('click', e => cbRef.current.onPick?.(e.latlng.lat, e.latlng.lng))
    mapRef.current = map
    setTimeout(() => map.invalidateSize(), 100)
    return () => { map.remove(); mapRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // markers / heat layer
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (layerRef.current) { map.removeLayer(layerRef.current); layerRef.current = null }

    if (heatmap) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const heat = (L as any).heatLayer(
        points.map(p => [p.lat, p.lng, 0.4 + (p.severity ?? 2) * 0.15]),
        { radius: 28, blur: 22, maxZoom: 16 })
      heat.addTo(map)
      layerRef.current = heat
      return
    }

    const group: L.MarkerClusterGroup | L.LayerGroup = cluster
      ? L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 46 })
      : L.layerGroup()
    points.forEach(p => {
      const sev = (p.severity ?? 0) as keyof typeof SEVERITY
      const color = SEVERITY[sev]?.color ?? '#64748b'
      const icon = L.divIcon({
        className: '', iconSize: [26, 26], iconAnchor: [13, 13],
        html: `<div class="marker-dot" style="width:26px;height:26px;background:${color}">${p.severity ?? ''}</div>`,
      })
      const m = L.marker([p.lat, p.lng], { icon, title: p.title })
      if (p.title) {
        m.bindPopup(`<div style="min-width:180px">
          <div style="font-weight:700;margin-bottom:2px">${p.title}</div>
          <div style="font-size:12px;color:#666">${p.category ?? ''} · ${p.status ?? ''}</div>
          <button data-cl-id="${p.id}" style="margin-top:6px;color:#0d8a50;font-weight:600;font-size:12px;cursor:pointer">View details →</button>
        </div>`)
        m.on('popupopen', e => {
          e.popup.getElement()?.querySelector('[data-cl-id]')?.addEventListener('click', () => cbRef.current.onMarkerClick?.(p.id))
        })
      }
      group.addLayer(m)
    })
    group.addTo(map)
    layerRef.current = group
  }, [points, heatmap, cluster])

  // picked location marker
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (pickRef.current) { map.removeLayer(pickRef.current); pickRef.current = null }
    if (picked) {
      const icon = L.divIcon({
        className: '', iconSize: [34, 34], iconAnchor: [17, 34],
        html: `<svg width="34" height="34" viewBox="0 0 24 24" fill="#0d8a50" stroke="white" stroke-width="1"><path d="M12 2C8 2 5 5 5 9c0 5 7 13 7 13s7-8 7-13c0-4-3-7-7-7z"/><circle cx="12" cy="9" r="2.6" fill="white"/></svg>`,
      })
      pickRef.current = L.marker(picked, { icon }).addTo(map)
      map.setView(picked, Math.max(map.getZoom(), 15))
    }
  }, [picked])

  useEffect(() => { mapRef.current?.setView(center) }, [center[0], center[1]]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} className={`${className} w-full`} role="application" aria-label="Issue map" />
}
