import anchors from './topology-anchors.json';
export type Anchor={x:number;y:number;width:number;height:number};

export function resolveTopologyLayout(saved:unknown):Record<string,Anchor> {
  const result:Record<string,Anchor>=Object.fromEntries(Object.entries(anchors).map(([id,value])=>[id,{...value}]));
  if(!saved || typeof saved!=='object' || Array.isArray(saved))return result;
  for(const [id,value] of Object.entries(saved)) {
    if(!Object.hasOwn(result,id) || !value || typeof value!=='object')continue;
    const a=value as Anchor;
    if(![a.x,a.y,a.width,a.height].every(v=>typeof v==='number' && Number.isFinite(v)))continue;
    if(a.x<0 || a.y<0 || a.width<=0 || a.height<=0 || a.x+a.width>100 || a.y+a.height>100)continue;
    result[id]={x:a.x,y:a.y,width:a.width,height:a.height};
  }
  return result;
}
