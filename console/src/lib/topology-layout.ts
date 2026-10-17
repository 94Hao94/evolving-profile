import anchors from './topology-anchors.json';
export type Anchor={x:number;y:number;width:number;height:number};
export const TOPOLOGY_CANVAS={width:1672,height:941,asset:'topology-reference-design-v17'} as const;
export const TOPOLOGY_LAYOUT_SCHEMA='evolving-profile.topology-layout.v1';
export type TopologyLayout={schema:typeof TOPOLOGY_LAYOUT_SCHEMA;canvas:typeof TOPOLOGY_CANVAS;revision:number;anchors:Record<string,Anchor>;texts:{en:Record<string,string>;zh:Record<string,string>};deleted:string[]};

export function validAnchor(value:unknown):value is Anchor {
  if(!value || typeof value!=='object')return false;
  const a=value as Anchor;
  return [a.x,a.y,a.width,a.height].every(v=>typeof v==='number' && Number.isFinite(v)) && a.x>=0 && a.y>=0 && a.width>0 && a.height>0 && a.x+a.width<=100 && a.y+a.height<=100;
}

export function resolveTopologyLayout(saved:unknown):Record<string,Anchor> {
  const result:Record<string,Anchor>=Object.fromEntries(Object.entries(anchors).map(([id,value])=>[id,{...value}]));
  if(saved && typeof saved==='object' && 'schema' in saved){
    const value=saved as TopologyLayout;
    if(value.schema!==TOPOLOGY_LAYOUT_SCHEMA || value.canvas?.asset!==TOPOLOGY_CANVAS.asset || value.canvas?.width!==TOPOLOGY_CANVAS.width || value.canvas?.height!==TOPOLOGY_CANVAS.height)return result;
    saved=value.anchors;
  }
  if(!saved || typeof saved!=='object' || Array.isArray(saved))return result;
  for(const [id,value] of Object.entries(saved)) {
    if(!Object.hasOwn(result,id) || !value || typeof value!=='object')continue;
    if(!validAnchor(value))continue;
    const a=value;
    result[id]={x:a.x,y:a.y,width:a.width,height:a.height};
  }
  return result;
}

export function defaultTopologyLayout():TopologyLayout {
  return {schema:TOPOLOGY_LAYOUT_SCHEMA,canvas:{...TOPOLOGY_CANVAS},revision:0,anchors:resolveTopologyLayout(null),texts:{en:{},zh:{}},deleted:['label-fork']};
}

export function topologyFailureView(previous:{layout:TopologyLayout;texts:Record<string,string>},cached:unknown,english:boolean) {
  let layout=validateTopologyLayout(previous.layout);
  try {const candidate=validateTopologyLayout(cached);if(candidate.revision>layout.revision)layout=candidate;}
  catch {/* An optional cache cannot invalidate the latest known shared layout. */}
  return {layout,texts:layout.texts[english?'en':'zh']};
}

/** Strict write validation; invalid settings must not overwrite the last good layout. */
export function validateTopologyLayout(input:unknown):TopologyLayout {
  if(!input || typeof input!=='object' || Array.isArray(input))throw new Error('invalid_layout');
  const value=input as TopologyLayout;
  if(value.schema!==TOPOLOGY_LAYOUT_SCHEMA || value.canvas?.asset!==TOPOLOGY_CANVAS.asset || value.canvas.width!==TOPOLOGY_CANVAS.width || value.canvas.height!==TOPOLOGY_CANVAS.height)throw new Error('layout_canvas_mismatch');
  if(!Number.isSafeInteger(value.revision) || value.revision<0)throw new Error('invalid_layout_revision');
  const defaults=defaultTopologyLayout();
  if(!value.anchors || typeof value.anchors!=='object' || Array.isArray(value.anchors))throw new Error('invalid_anchors');
  for(const [id,anchor] of Object.entries(value.anchors))if(!Object.hasOwn(defaults.anchors,id) || !validAnchor(anchor))throw new Error('invalid_anchor');
  const texts:TopologyLayout['texts']={en:{},zh:{}};
  if(!value.texts || typeof value.texts!=='object' || Array.isArray(value.texts))throw new Error('invalid_layout_texts');
  for(const locale of Object.keys(value.texts)){
    if(locale!=='en' && locale!=='zh')throw new Error('invalid_layout_locale');
    const entries=value.texts[locale];
    if(!entries || typeof entries!=='object' || Array.isArray(entries))throw new Error('invalid_layout_texts');
    for(const [id,text] of Object.entries(entries)){
      if(!Object.hasOwn(defaults.anchors,id) || typeof text!=='string' || text.length>200 || /[\u0000-\u001f]/.test(text))throw new Error('invalid_layout_text');
      texts[locale][id]=text;
    }
  }
  if(!Array.isArray(value.deleted) || value.deleted.length>Object.keys(defaults.anchors).length || value.deleted.some(id=>typeof id!=='string' || !Object.hasOwn(defaults.anchors,id)))throw new Error('invalid_layout_deleted');
  return {schema:TOPOLOGY_LAYOUT_SCHEMA,canvas:{...TOPOLOGY_CANVAS},revision:value.revision,anchors:resolveTopologyLayout(value.anchors),texts,deleted:[...new Set(value.deleted)]};
}
