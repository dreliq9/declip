#include "../common/media_kernel_bakeoff.h"
#include <algorithm>
#include <cstring>
#include <numeric>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

struct Clip { std::string asset; mk_time_t source_in; mk_time_t duration; mk_time_t transition; };
struct Proposal { uint64_t id; uint64_t base_revision; size_t clip_index; mk_time_t new_duration; };
struct mk_project {
  uint64_t revision{0};
  uint64_t next_proposal{1};
  std::unordered_map<std::string, mk_time_t> assets;
  std::vector<Clip> clips;
  std::unordered_map<uint64_t, Proposal> proposals;
};

static bool norm(mk_time_t in, mk_time_t &out) {
  if (in.den == 0) return false;
  if (in.num == 0) { out = {0,1}; return true; }
  if (in.den < 0) {
    if (in.den == INT64_MIN || in.num == INT64_MIN) return false;
    in.den = -in.den; in.num = -in.num;
  }
  auto an = in.num < 0 ? uint64_t(-(in.num + 1)) + 1 : uint64_t(in.num);
  auto ad = uint64_t(in.den);
  uint64_t g = std::gcd(an, ad);
  out = {in.num / static_cast<int64_t>(g), in.den / static_cast<int64_t>(g)};
  return true;
}
static bool positive(mk_time_t t) { mk_time_t n; return norm(t,n) && n.num > 0; }
static int cmp(mk_time_t a, mk_time_t b) {
  mk_time_t na, nb; if (!norm(a,na) || !norm(b,nb)) return 0;
  __int128 l = (__int128)na.num * nb.den, r = (__int128)nb.num * na.den;
  return (l>r) - (l<r);
}
static bool add(mk_time_t a, mk_time_t b, mk_time_t &out) {
  mk_time_t na, nb; if (!norm(a,na)||!norm(b,nb)) return false;
  __int128 n=(__int128)na.num*nb.den+(__int128)nb.num*na.den;
  __int128 d=(__int128)na.den*nb.den;
  if(n>INT64_MAX||n<INT64_MIN||d>INT64_MAX) return false;
  return norm({(int64_t)n,(int64_t)d},out);
}
static bool valid_clip(const mk_project* p, const Clip& c) {
  auto it=p->assets.find(c.asset); if(it==p->assets.end()||!positive(c.duration)) return false;
  mk_time_t end; if(!add(c.source_in,c.duration,end)) return false;
  if(cmp(c.source_in,{0,1})<0 || cmp(end,it->second)>0) return false;
  if(c.transition.num != 0 && (!positive(c.transition)||cmp(c.transition,c.duration)>=0)) return false;
  return true;
}
static std::string rat(mk_time_t t){ mk_time_t n; norm(t,n); return std::to_string(n.num)+"/"+std::to_string(n.den); }

extern "C" {
mk_status_t mk_time_normalize(mk_time_t in,mk_time_t*out){ if(!out)return MK_INVALID; return norm(in,*out)?MK_OK:MK_INVALID; }
mk_status_t mk_time_add(mk_time_t a,mk_time_t b,mk_time_t*out){ if(!out)return MK_INVALID; return add(a,b,*out)?MK_OK:MK_OVERFLOW; }
int mk_time_compare(mk_time_t a,mk_time_t b){return cmp(a,b);}
mk_project_t* mk_project_create(void){ try{return new mk_project();}catch(...){return nullptr;} }
void mk_project_destroy(mk_project_t*p){delete p;}
uint64_t mk_project_revision(const mk_project_t*p){return p?p->revision:0;}
mk_status_t mk_project_add_asset(mk_project_t*p,const char*id,mk_time_t duration){ if(!p||!id||!*id||!positive(duration))return MK_INVALID; mk_time_t n;norm(duration,n); auto [it,ok]=p->assets.emplace(id,n); return ok?MK_OK:MK_CONFLICT;}
mk_status_t mk_project_append_clip(mk_project_t*p,const char*asset,mk_time_t source,mk_time_t duration,mk_time_t transition){if(!p||!asset)return MK_INVALID; mk_time_t ns,nd,nt; if(!norm(source,ns)||!norm(duration,nd)||!norm(transition,nt))return MK_INVALID; Clip c{asset,ns,nd,nt}; if(!valid_clip(p,c))return MK_INVALID; if(p->clips.empty()&&nt.num!=0)return MK_INVALID; p->clips.push_back(std::move(c)); return MK_OK;}
mk_status_t mk_project_propose_trim(mk_project_t*p,uint64_t base,size_t idx,mk_time_t dur,uint64_t*out){if(!p||!out||base!=p->revision)return base==p->revision?MK_INVALID:MK_CONFLICT; if(idx>=p->clips.size()||!positive(dur))return MK_INVALID; mk_time_t nd;norm(dur,nd); Clip c=p->clips[idx];c.duration=nd;if(!valid_clip(p,c))return MK_INVALID;uint64_t id=p->next_proposal++;p->proposals.emplace(id,Proposal{id,base,idx,nd});*out=id;return MK_OK;}
mk_status_t mk_project_commit(mk_project_t*p,uint64_t id,uint64_t*out){if(!p||!out)return MK_INVALID;auto it=p->proposals.find(id);if(it==p->proposals.end())return MK_NOT_FOUND;auto pr=it->second;if(pr.base_revision!=p->revision)return MK_CONFLICT;Clip c=p->clips[pr.clip_index];c.duration=pr.new_duration;if(!valid_clip(p,c))return MK_INVALID;p->clips[pr.clip_index]=c;p->revision++;p->proposals.clear();*out=p->revision;return MK_OK;}
mk_status_t mk_project_lower_ffmpeg(const mk_project_t*p,char*buf,size_t cap,size_t*needed){if(!p||!needed)return MK_INVALID;std::ostringstream s;s<<"ffmpeg";for(auto &c:p->clips)s<<" -i "<<c.asset;s<<" -filter_complex \"";for(size_t i=0;i<p->clips.size();++i){auto &c=p->clips[i];if(i)s<<";";s<<"["<<i<<":v]trim=start="<<rat(c.source_in)<<":duration="<<rat(c.duration)<<"[v"<<i<<"]";}for(size_t i=1;i<p->clips.size();++i){auto &c=p->clips[i];if(c.transition.num!=0)s<<";[v"<<i-1<<"][v"<<i<<"]xfade=duration="<<rat(c.transition)<<"[x"<<i<<"]";}s<<"\" out.mp4";std::string x=s.str();*needed=x.size()+1;if(!buf||cap<*needed)return MK_BUFFER_TOO_SMALL;std::memcpy(buf,x.c_str(),*needed);return MK_OK;}
uint64_t mk_benchmark(uint64_t iters){mk_time_t x{1001,30000},y{1,48000},z;uint64_t sum=0;for(uint64_t i=0;i<iters;++i){if(!add(x,y,z))break;sum^=(uint64_t)z.num+(uint64_t)z.den+i;x=(i&1)?mk_time_t{1001,30000}:mk_time_t{1,24};}return sum;}
}
