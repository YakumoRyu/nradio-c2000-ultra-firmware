import argparse,json,subprocess,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args();code=args.source.read_text();start=code.index('static int\npci_dma_rx_poll(');end=code.index('\nstatic ',start+12);function=code[start:end]
prefix=r'''
#include <assert.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
typedef unsigned int u32;
struct napi_struct { void *dev; };
struct pci_trans;
struct pci_queue { struct napi_struct napi; u32 head,tail,q_size,hw_didx_addr,hw_didx_mask,hw_int_mask; int vec_id; };
struct pci_ops { int (*process)(struct pci_trans *,struct pci_queue *,int); };
struct pci_rx_queue { struct pci_queue q; struct pci_ops *q_ops; };
struct pci_irq_vector_data { int unused; };
struct pci_trans { int napi_dev; struct pci_irq_vector_data vec_data[1]; };
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
#define to_bus_trans(x) (x)
static unsigned producer;
static int mode, calls, completed, irq_enabled, actual_done;
static bool allow_complete;
static unsigned bus_get_field(struct pci_trans *t,unsigned addr,unsigned mask) {(void)t;(void)addr;(void)mask;return producer;}
static void mt_rcu_read_lock(void) {}
static void mt_rcu_read_unlock(void) {}
static bool napi_complete_done(struct napi_struct *n,int done) {(void)n;completed++;actual_done=done;return allow_complete;}
static void pci_dma_irq_enable(struct pci_irq_vector_data *v,unsigned mask) {(void)v;(void)mask;irq_enabled++;}
static int process(struct pci_trans *t,struct pci_queue *q,int budget) {
 (void)t;calls++;
 if (mode==0 || calls>1 || !budget)return 0;
 if(mode==1){q->head++;return 1;}
 if(mode==2){q->head+=budget;return budget;}
 if(mode==3){q->head++;return 0;}
 return 0;
}
'''
suffix=r'''
static struct pci_trans trans;
static struct pci_ops ops={.process=process};
static struct pci_rx_queue rq;
static void reset(int m,unsigned tail) {
 rq=(struct pci_rx_queue){.q={.head=7,.q_size=1024,.hw_int_mask=1},.q_ops=&ops};
 rq.q.napi.dev=&trans.napi_dev;mode=m;producer=tail;calls=completed=irq_enabled=actual_done=0;allow_complete=true;
}
int main(void) {
 reset(0,12);assert(pci_dma_rx_poll(&rq.q.napi,64)==0);assert(completed==1&&irq_enabled==1&&actual_done==0&&calls==1);
 reset(1,9);assert(pci_dma_rx_poll(&rq.q.napi,64)==1);assert(completed==1&&irq_enabled==1&&actual_done==1);
 reset(1,12);assert(pci_dma_rx_poll(&rq.q.napi,64)==64);assert(completed==0&&irq_enabled==0);
 mode=0;assert(pci_dma_rx_poll(&rq.q.napi,64)==0);assert(completed==1&&irq_enabled==1);
 reset(2,400);assert(pci_dma_rx_poll(&rq.q.napi,64)==64);assert(completed==0&&irq_enabled==0);
 reset(0,12);allow_complete=false;assert(pci_dma_rx_poll(&rq.q.napi,64)==0);assert(completed==1&&irq_enabled==0);
 reset(3,12);assert(pci_dma_rx_poll(&rq.q.napi,64)==64);assert(completed==0&&irq_enabled==0);
 reset(0,8);assert(pci_dma_rx_poll(&rq.q.napi,0)==0);assert(completed==0&&irq_enabled==0);
 puts("PASS: 7 NAPI progress/completion cases");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    source=Path(tmp)/'poll.c';exe=Path(tmp)/'poll'
    source.write_text(prefix+function+suffix)
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(exe)],check=True)
    result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)

print(result.stdout.strip())
