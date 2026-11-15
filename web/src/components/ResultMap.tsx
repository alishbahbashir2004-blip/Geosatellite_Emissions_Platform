// Renders a server-built map descriptor with react-leaflet. Gas-specific
// styling (palette, labels, tooltips) is already resolved server-side.

import { useEffect, useMemo } from 'react'
import {
  LayersControl, MapContainer, Marker, Polyline, Rectangle, TileLayer,
  Tooltip, useMap,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { MapBox, MapDescriptor } from '../types'

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/' +
  'World_Imagery/MapServer/tile/{z}/{y}/{x}'
const OSM = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'

function bounds(b: { N: number; S: number; W: number; E: number }):
  [[number, number], [number, number]] {
  return [[b.S, b.W], [b.N, b.E]]
}

/** Refits whenever the descriptor's box changes — a new query, a new area. */
function FitTo({ box }: { box: MapDescriptor['fit'] }) {
  const map = useMap()
  const key = `${box.N},${box.S},${box.W},${box.E}`
  useEffect(() => { map.fitBounds(bounds(box)) }, [map, key])
  return null
}

function BoxShape({ box }: { box: MapBox }) {
  return (
    <>
      <Rectangle
        bounds={bounds(box.bbox)}
        pathOptions={{
          color: box.color, weight: box.weight, opacity: 0.95,
          fill: box.fillOpacity > 0, fillColor: box.color,
          fillOpacity: box.fillOpacity,
          dashArray: box.dash ?? undefined,
        }}
      >
        {box.tooltip && (
          <Tooltip sticky>
            <span dangerouslySetInnerHTML={{ __html: box.tooltip }} />
          </Tooltip>
        )}
      </Rectangle>
      {box.badge && (
        // Pinned to top-left so patches are distinguishable without hovering;
        // pointer-events off so it doesn't block the box's own hover.
        <Marker
          position={[box.bbox.N, box.bbox.W]}
          interactive={false}
          icon={L.divIcon({
            className: '',
            html: `<div style="font:600 11px/1 sans-serif;color:#fff;
              background:${box.color};border-radius:3px;padding:2px 5px;
              display:inline-block;white-space:nowrap;pointer-events:none;">
              ${box.badge}</div>`,
          })}
        />
      )}
    </>
  )
}

function ColorBar({ bar }: { bar: NonNullable<MapDescriptor['colorbar']> }) {
  const gradient = `linear-gradient(to right, ${bar.colors.join(',')})`
  return (
    <div className="leaflet-top leaflet-right" style={{ pointerEvents: 'none' }}>
      <div className="leaflet-control colorbar">
        <div>{bar.caption}</div>
        <div className="strip" style={{ background: gradient }} />
        <div className="ends">
          <span>{bar.vmin.toFixed(1)}</span><span>{bar.vmax.toFixed(1)}</span>
        </div>
      </div>
    </div>
  )
}

function ClassLegend({ legend }: {
  legend: NonNullable<MapDescriptor['classLegend']>
}) {
  // Equal-width swatches, not scaled — classes step by ~3x each, so a
  // proportional bar would make most of them unreadable slivers.
  return (
    <div className="leaflet-bottom leaflet-left" style={{ pointerEvents: 'none' }}>
      <div className="leaflet-control class-legend">
        <div style={{ fontSize: 10, fontWeight: 600, paddingBottom: 4 }}>
          {legend.title}
        </div>
        <div className="swatches">
          {legend.classes.map((c, i) => (
            <div key={i}>
              <div className="sw" style={{ background: c.color }} />
              <div className="tick">
                {c.high === null
                  ? `>${c.low.toLocaleString()}`
                  : c.high.toLocaleString()}
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 9, color: '#666', paddingTop: 4 }}>
          {legend.note}
        </div>
      </div>
    </div>
  )
}

export function ResultMap({ descriptor, maxHotspots }: {
  descriptor: MapDescriptor
  maxHotspots?: number
}) {
  // Server returns every patch found; the slider controls how many are drawn.
  const hotspots = useMemo(() => {
    const all = descriptor.hotspotBoxes ?? []
    return maxHotspots === undefined ? all : all.slice(0, maxHotspots)
  }, [descriptor.hotspotBoxes, maxHotspots])

  return (
    <div className="map">
      <MapContainer bounds={bounds(descriptor.fit)} scrollWheelZoom>
        <FitTo box={descriptor.fit} />
        <LayersControl position="topright" collapsed={false}>
          <LayersControl.BaseLayer name="Street map" checked>
            <TileLayer url={OSM} attribution="&copy; OpenStreetMap" />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Satellite">
            <TileLayer url={ESRI} attribution="Esri, Maxar, Earthstar Geographics" />
          </LayersControl.BaseLayer>
          {descriptor.tiles.map((tile) => (
            <LayersControl.Overlay key={tile.url} name={tile.name} checked={tile.show}>
              <TileLayer url={tile.url} opacity={tile.opacity}
                         attribution="NASA GHG Center / Google Earth Engine" />
            </LayersControl.Overlay>
          ))}
        </LayersControl>

        {descriptor.lines.map((line, i) => (
          <Polyline key={i} positions={line.coords}
                    pathOptions={{ color: line.color, weight: line.weight,
                                   opacity: line.opacity }} />
        ))}
        {descriptor.boxes.map((box, i) => <BoxShape key={`b${i}`} box={box} />)}
        {hotspots.map((box, i) => <BoxShape key={`h${i}`} box={box} />)}

        {descriptor.colorbar && <ColorBar bar={descriptor.colorbar} />}
        {descriptor.classLegend && <ClassLegend legend={descriptor.classLegend} />}
      </MapContainer>
    </div>
  )
}
