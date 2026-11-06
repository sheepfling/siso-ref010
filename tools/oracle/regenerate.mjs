import ts from 'typescript';
import fs from 'node:fs';
import path from 'node:path';
const base=path.dirname(new URL(import.meta.url).pathname);
for(const pkg of ['lib','parser']) {
 const source=path.join(base,'../../vendor/upstream/packages',pkg,'src');
 const dest=path.join(base,'_oracle-build/upstream-'+pkg); fs.mkdirSync(dest,{recursive:true});
 fs.writeFileSync(path.join(dest,'package.json'),JSON.stringify({type:'module'}));
 for(const name of fs.readdirSync(source,{recursive:true})) {
  if(!name.endsWith('.ts') || name.includes('test') || name.endsWith('.d.ts')) continue;
  const input=fs.readFileSync(path.join(source,name),'utf8').replaceAll('"@siso-entity-type/lib"','"../upstream-lib/index.js"');
  const result=ts.transpileModule(input,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}});
  const output=path.join(dest,name.replace(/\.ts$/,'.js'));fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,result.outputText);
 }
}
const {SisoEnums,SisoEnum,Utils}=await import('./_oracle-build/upstream-lib/index.js');
const {SisoEnumsFactory}=await import('./_oracle-build/upstream-parser/index.js');
const Long=(await import('long')).default;
const data=JSON.parse(fs.readFileSync(path.join(base,'../../src/siso_entity_type/data/siso-enums.json'),'utf8'));
const catalog=new SisoEnums(data);
const keys=[...new Set([...Object.keys(data.categories),...Object.keys(data.subcategories)])];
const tests={upstream_commit:'bb195c647b6f9c4b7bea4e5a10e6c560a0b0bceb',counts:{countries:catalog.countryCount,kinds:catalog.kindCount,domains:catalog.domainCount,categories:catalog.categoryCount,subcategories:catalog.subcategoryCount}, all:[], detailed:[], domains:[], collections:[]};
for (const key of keys) {const e=SisoEnum.fromKey(Long.fromString(key)); tests.all.push([key,e.toString(),e.toKey().toString(),catalog.getDescriptionOf(e)]);}
for(let i=0;i<keys.length;i+=97) {
 const e=SisoEnum.fromKey(Long.fromString(keys[i]));
 for (const f of [e,new SisoEnum(e.kind,e.domain,65535,e.category,e.subcategory,e.specific,255)]) {
  tests.detailed.push([f.toString(),catalog.getDescriptionOf(f),catalog.getDescriptionOf(f,true),catalog.getCountryName(f),catalog.getKindName(f),catalog.getDomainName(f)]);
 }
 if(i%3===0) {
 const args=[e.kind,e.domain,e.country,e.category,e.subcategory,e.specific];
 for(const [name,n] of [['getAllCategoriesOf',3],['getAllSubcategoriesOf',4],['getAllSpecificsOf',5],['getAllExtrasOf',6]]) tests.collections.push([name,args.slice(0,n),[...catalog[name](...args.slice(0,n))]]);
 }
}
for(let kind=0;kind<11;kind++)tests.domains.push([kind,[...catalog.getAllDomainsOf(kind)]]);
tests.allDomains=[...catalog.getAllDomains()];
tests.search=['F803 Tromp','MC-12S-1 EMARSS-G','f/a-18','nonexistentxyz'].map(q=>[q,catalog.searchDescription(q)]);
const parser=SisoEnumsFactory.createFromString(fs.readFileSync(path.join(base,'../../tests/fixtures/siso-ref-010-v35.xml'),'utf8'));
parser.writeOutputFiles(path.join(base,'_oracle-build/parsed'));
const parsed=JSON.parse(fs.readFileSync(path.join(base,'_oracle-build/parsed/siso-enums.json'),'utf8'));
const equality=Object.keys(data).every(name=>JSON.stringify(data[name])===JSON.stringify(parsed[name]));
console.log('Upstream parser exact map-order JSON parity:',equality);
if(!equality)throw new Error('Upstream parser mismatch');
fs.writeFileSync(path.join(base,'../../tests/fixtures/upstream-oracle.json'),JSON.stringify(tests));
console.log(JSON.stringify({keys:tests.all.length,detailed:tests.detailed.length,collections:tests.collections.length}));
