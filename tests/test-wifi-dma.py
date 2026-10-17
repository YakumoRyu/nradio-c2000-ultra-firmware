import argparse,json,subprocess,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args();code=args.source.read_text()
begin=code.index('static int\npci_dma_rx_desc_fault(');end=code.index('\n\nstatic inline int\npci_dma_get_buf',begin)
function=code[begin:end]
begin=code.index('static int\npci_dma_dequeue(');end=code.index('\nvoid\npci_dma_gather_frag',begin);dequeue=code[begin:end]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef unsigned u32;
typedef uintptr_t dma_addr_t;
#define HZ 1
#define HW_SER_LV_10_0 100
#define SKB_HEADROOM_RSV 64
#define DMA_FROM_DEVICE 0
#define unlikely(x) (x)
#define BIT(x) (1U << (x))
#define cpu_to_le32(x) (x)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define GET_PKT_IO 1
#define PCI_FLAG_WHNAT_TX 0
#define Q_RX_EVENT_TX_FREE_DONE 5
#define RXDMAD_DDONE_SHIFT 31
#define RXDMAD_M_DONE_SHIFT 30
struct rate { unsigned next; };
#define DEFINE_RATELIMIT_STATE(name,interval,burst) struct rate name={0}
static unsigned now=1;
static int __ratelimit(struct rate *r) {if(now<r->next)return 0;r->next=now+30;return 1;}
struct pci_dma_desc {u32 dw0,dw1,dw2,dw3;};
struct pci_dma_buf {void *alloc_va;dma_addr_t alloc_pa;int alloc_size;};
struct pci_dma_cb {void *alloc_va,*pkt;struct pci_dma_buf dma_buf;};
struct pci_queue {struct pci_dma_cb *cb;u32 head,tail,q_size;int q_attr;char *q_info;};
struct pci_rx_queue {struct pci_queue q;int magic_cnt,get_pkt_method;};
struct chip {u32 device_id;};
struct mtk_hw_dev {struct chip *chip_drv;struct {unsigned idx;}sys_idx;};
struct pci_trans {struct mtk_hw_dev dev;unsigned long flags;};
struct mtk_bus_rx_info {void *pkt;dma_addr_t sdp0;u32 id;};
static struct pci_dma_desc desc;
static struct pci_dma_cb cb[2];
static struct pci_rx_queue rq;
static struct pci_trans trans;
static struct chip chip={0x7992};
static unsigned char source[4096],destination[4096];
static int fault_count,allocs,lookup_count,syncs,refills,barriers;
static int lookup_error,null_pkt,null_va,bad_offset,no_memory,expect_barrier;
static dma_addr_t descriptor_pa=0x12340000;
#define to_device(t) ((void *)(t))
#define to_hw_dev(t) (&(t)->dev)
#define to_rx_tk_mgmt(t) ((void *)(t))
static void test_log(void *device, const char *fmt, ...) {(void)device;(void)fmt;}
#define dev_err(...) test_log(__VA_ARGS__)
#define dev_err_once(...) test_log(__VA_ARGS__)
static int mtk_bus_rx_ser_event(struct mtk_hw_dev *d,u32 chipid,u32 level,u32 event,u32 hwid) {
 (void)d;assert(chipid==0x7992&&level==100&&event==0&&hwid==0);fault_count++;return 0;
}
static int pci_dma_rxdmad_parser(struct pci_trans *t,struct pci_rx_queue *r,struct pci_dma_desc *d,struct mtk_bus_rx_info *i) {
 (void)t;(void)r;(void)d;if(expect_barrier)assert(barriers>0);i->sdp0=descriptor_pa;i->id=0;return 0;
}
static int mtk_rx_tk_entry_find(void *m,u32 id,void **pkt,void **va,dma_addr_t *pa) {
 (void)m;assert(id==0);lookup_count++;if(lookup_error)return -EINVAL;
 *pkt=null_pkt?NULL:source;*va=null_va?NULL:source+(bad_offset?128:16);*pa=0x12340000;return 0;
}
static void *pci_dma_rx_pkt_alloc(void *d,struct pci_rx_queue *r,struct pci_dma_buf *buf,bool map) {
 (void)d;(void)r;(void)buf;assert(!map);allocs++;return no_memory?NULL:destination;
}
static void dma_sync_single_for_cpu(void *d,dma_addr_t p,int n,int direction) {(void)d;(void)p;(void)n;(void)direction;syncs++;}
static void dma_sync_single_for_device(void *d,dma_addr_t p,int n,int direction) {(void)d;(void)p;(void)n;(void)direction;syncs++;}
#define rx_pkt_total_size(n) (n)
static void clear_ddone(void *v) {(void)v;}
static void fill_rxd(struct pci_dma_cb *c,u32 id,u32 magic) {(void)c;(void)id;(void)magic;refills++;}
static int test_bit(int n,unsigned long *flags) {return !!(*flags&BIT(n));}
static void dma_rmb(void) {barriers++;}
static int pci_dma_get_buf(struct pci_trans *t,struct pci_queue *q,u32 idx,struct mtk_bus_rx_info *i) {
 int rc=pci_dma_get_data_buf_by_copy(t,q,idx,i);if(!rc)q->head=idx;return rc;
}
'''
# Forward declaration keeps the real copy function below the mocks.
forward='static int pci_dma_get_data_buf_by_copy(struct pci_trans *,struct pci_queue *,u32,struct mtk_bus_rx_info *);\n'
prefix=prefix.replace('static int pci_dma_get_buf(',forward+'static int pci_dma_get_buf(')
suffix=r'''
static void reset(void) {
 now+=31;fault_count=allocs=lookup_count=syncs=refills=barriers=0;
 lookup_error=null_pkt=null_va=bad_offset=no_memory=expect_barrier=0;
 descriptor_pa=0x12340000;memset(cb,0,sizeof(cb));memset(&desc,0,sizeof(desc));
 cb[0].alloc_va=cb[1].alloc_va=&desc;cb[0].dma_buf.alloc_size=cb[1].dma_buf.alloc_size=1024;
 rq=(struct pci_rx_queue){.q={.cb=cb,.q_size=2,.q_info="test-rx"}};
 trans=(struct pci_trans){.dev={.chip_drv=&chip}};
 memset(source,0x5a,sizeof(source));memset(destination,0,sizeof(destination));
}
static int copy(void) {struct mtk_bus_rx_info info={0};return pci_dma_get_data_buf_by_copy(&trans,&rq.q,0,&info);}
int main(void) {
 struct mtk_bus_rx_info info={0};
 reset();descriptor_pa=0;assert(copy()==-EINVAL);assert(fault_count==1&&lookup_count==0&&allocs==0&&refills==0);
 assert(copy()==-EINVAL);assert(fault_count==1);now+=30;assert(copy()==-EINVAL);assert(fault_count==2);
 reset();lookup_error=1;assert(copy()==-EINVAL);assert(fault_count==1&&allocs==0&&refills==0);
 reset();null_pkt=1;assert(copy()==-EINVAL);assert(fault_count==1&&allocs==0);
 reset();null_va=1;assert(copy()==-EINVAL);assert(fault_count==1&&allocs==0);
 reset();bad_offset=1;assert(copy()==-EINVAL);assert(fault_count==1&&allocs==0&&syncs==0);
 reset();descriptor_pa++;assert(copy()==-EINVAL);assert(fault_count==1&&allocs==0&&syncs==0&&refills==0);
 reset();no_memory=1;assert(copy()==-ENOMEM);assert(fault_count==0&&allocs==1&&refills==0);
 reset();assert(copy()==0);assert(fault_count==0&&allocs==1&&refills==1&&syncs==2);assert(destination[48]==0x5a);
 reset();assert(pci_dma_dequeue(&trans,&rq.q,false,&info)==-EINVAL);assert(barriers==0&&lookup_count==0);
 reset();desc.dw1=BIT(31);expect_barrier=1;assert(pci_dma_dequeue(&trans,&rq.q,false,&info)==0);assert(barriers==1&&refills==1);
 reset();desc.dw1=BIT(31);trans.flags=1;rq.q.q_attr=5;assert(pci_dma_dequeue(&trans,&rq.q,false,&info)==-EINVAL);assert(barriers==0);
 desc.dw1|=BIT(30);expect_barrier=1;assert(pci_dma_dequeue(&trans,&rq.q,false,&info)==0);assert(barriers==1);
 reset();rq.get_pkt_method=GET_PKT_IO;rq.q.tail=1;assert(pci_dma_dequeue(&trans,&rq.q,false,&info)==-EINVAL);assert(barriers==0);
 reset();expect_barrier=1;assert(pci_dma_dequeue(&trans,&rq.q,true,&info)==0);assert(barriers==1&&(desc.dw1&BIT(31)));
 puts("PASS: 14 malformed RX, DMA ownership, recovery rate and normal-copy scenarios");
}
'''
with tempfile.TemporaryDirectory() as d:
    src=Path(d)/'rx.c';exe=Path(d)/'rx';src.write_text(prefix+function+dequeue+suffix)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-O2','-fsanitize=undefined,address',str(src),'-o',str(exe)],check=True)
    result=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
report={'passed':True,'scenarios':14,'actual_patched_functions_compiled':True,'address_and_undefined_sanitizers':True,'stdout':result.stdout.strip()}
print(json.dumps(report))
