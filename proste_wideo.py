"""PROSTE WIDEO — straightforward desktop video editor."""
from __future__ import annotations
import copy
import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image,ImageTk
from proste_wideo_core import Mask, apply_masks, clamp_box, export_video, split_segment, track_range

INK='#080808'; PANEL='#151515'; PANEL2='#202020'; ACCENT='#5A5A5A'; WHITE='#DCDCDC'; MUTED='#999999'; GRAY='#343434'

class ProsteWideo:
    def __init__(self,root):
        self.root=root;root.title('PROSTE WIDEO')
        root.geometry('1440x900');root.minsize(1050,720);root.configure(bg=INK)
        self.path=None;self.cap=None;self.frames=0;self.fps=25.0;self.width=0;self.height=0
        self.pos=0;self.masks=[];self.selected=-1;self.segments=[]
        self.playing=False;self.play_mark=0;self.task=None;self.events=queue.Queue()
        self.photo=None;self.canvas_geometry=(1,0,0);self.mouse=None;self.is_seek=False
        self._suppress=False;self.tile_rects=[];self.tile_down=None;self.segment_thumb_cache={};self.build();self.root.after(60,self.poll_events)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.bind('<Control-s>',lambda e:self.save_project())
        self.root.bind('<Control-o>',lambda e:self.open_video())
        self.root.bind_all('<KeyPress-space>',self.on_space)
        self.root.bind_all('<KeyPress-b>',self.on_cut_hotkey)
        self.root.bind_all('<KeyPress-B>',self.on_cut_hotkey)

    def on_space(self,event):
        if isinstance(event.widget,(tk.Entry,ttk.Combobox,tk.Text)):
            return None
        self.toggle_play()
        return 'break'

    def on_cut_hotkey(self,event):
        if isinstance(event.widget,(tk.Entry,ttk.Combobox,tk.Text)):
            return None
        self.cut_here()
        return 'break'

    def makebutton(self,parent,label,action,accent=False):
        return tk.Button(parent,text=label,command=action,bg='#414141' if accent else '#292929',
                         fg=WHITE,activebackground='#555555',activeforeground='#F5F5F5',
                         font=('Segoe UI',10),padx=12,pady=8,relief='flat',bd=0,cursor='hand2',
                         highlightthickness=0)

    def label(self,parent,text,color=MUTED,size=10,bold=False):
        return tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,
                        font=('Segoe UI',size,'bold' if bold else 'normal'),anchor='w')

    def frame(self,parent,bg=PANEL): return tk.Frame(parent,bg=bg)

    def heading(self,parent,text):
        widget=self.label(parent,text,WHITE,10,True)
        widget.pack(fill='x',padx=12,pady=(15,8))
        return widget

    def build(self):
        header=self.frame(self.root,INK);header.pack(fill='x',padx=16,pady=(13,10))
        self.label(header,'PROSTE WIDEO',WHITE,20,True).pack(side='left')
        self.makebutton(header,'Otwórz film',self.open_video,True).pack(side='left',padx=(24,6))
        self.makebutton(header,'Otwórz projekt',self.open_project).pack(side='left',padx=(0,6))
        self.makebutton(header,'Zapisz projekt',self.save_project).pack(side='left')
        self.status_text=tk.StringVar(value='Gotowy')
        tk.Label(header,textvariable=self.status_text,fg=MUTED,bg=INK,font=('Segoe UI',9)).pack(side='right')

        body=self.frame(self.root,INK);body.pack(fill='both',expand=True,padx=16,pady=(0,12))
        left=self.frame(body,INK);left.pack(side='left',fill='both',expand=True,padx=(0,12))
        right=self.frame(body,PANEL);right.pack(side='right',fill='y');right.configure(width=306);right.pack_propagate(False)

        self.canvas=tk.Canvas(left,bg='#050505',highlightthickness=1,highlightbackground='#242424',cursor='crosshair')
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.render())
        self.canvas.bind('<ButtonPress-1>',self.mouse_down)
        self.canvas.bind('<B1-Motion>',self.mouse_move)
        self.canvas.bind('<ButtonRelease-1>',self.mouse_up)

        controls=self.frame(left,INK);controls.pack(fill='x',pady=(8,3))
        for title,act in [('◀',lambda:self.seek(self.pos-1)),('▶ / II',self.toggle_play),('▶',lambda:self.seek(self.pos+1)),
                          ('B  |  Tnij',self.cut_here),('Klatka kluczowa',self.add_key)]:
            self.makebutton(controls,title,act).pack(side='left',padx=(0,5))
        self.label(controls,'Spacja: odtwarzaj / pauza',MUTED,9).pack(side='right')

        seeker=self.frame(left,INK);seeker.pack(fill='x',pady=(0,4))
        self.timeline=tk.Scale(seeker,from_=0,to=0,orient='horizontal',bg=INK,fg=WHITE,troughcolor=GRAY,
                               highlightthickness=0,bd=0,showvalue=False,activebackground='#777777',command=self.slider_move)
        self.timeline.pack(side='left',fill='x',expand=True)
        self.frame_text=tk.StringVar(value='00:00 / 00:00')
        tk.Label(seeker,textvariable=self.frame_text,bg=INK,fg=MUTED,font=('Consolas',10)).pack(side='right',padx=(8,0))

        tilebar=self.frame(left,INK);tilebar.pack(fill='x',pady=(4,3))
        self.label(tilebar,'Oś czasu',WHITE,11,True).pack(side='left')
        for title,act in [('◀ Przesuń',lambda:self.move_part(-1)),('Przesuń ▶',lambda:self.move_part(1)),('Usuń',self.delete_part)]:
            self.makebutton(tilebar,title,act).pack(side='right',padx=(5,0))
        timeline_area=self.frame(left,INK);timeline_area.pack(fill='x')
        self.tiles=tk.Canvas(timeline_area,height=112,bg='#101010',highlightthickness=1,highlightbackground='#252525',cursor='hand2')
        self.tiles.pack(side='top',fill='x',expand=True)
        self.tile_scroll=tk.Scrollbar(timeline_area,orient='horizontal',command=self.tiles.xview)
        self.tile_scroll.pack(side='bottom',fill='x')
        self.tiles.configure(xscrollcommand=self.tile_scroll.set)
        self.tiles.bind('<ButtonPress-1>',self.tile_press)
        self.tiles.bind('<ButtonRelease-1>',self.tile_release)
        self.tiles.bind('<B1-Motion>',self.tile_motion)
        self.tiles.bind('<MouseWheel>',self.tile_wheel)
        self.tiles.bind('<Button-4>',lambda e:self.tiles.xview_scroll(-2,'units'))
        self.tiles.bind('<Button-5>',lambda e:self.tiles.xview_scroll(2,'units'))
        # A hidden selection adapter preserves existing editor helpers/tests and keyboard actions.
        self.partlist=ttk.Treeview(left,columns=('order','start','end','duration'),show='headings',height=1,selectmode='browse')
        self.partlist.bind('<<TreeviewSelect>>',self.part_selected)

        self.heading(right,'Maski')
        self.masklist=tk.Listbox(right,bg='#222222',fg=WHITE,selectbackground='#555555',
                                 selectforeground='#FFFFFF',highlightthickness=0,relief='flat',height=4,font=('Segoe UI',10))
        self.masklist.pack(fill='x',padx=12);self.masklist.bind('<<ListboxSelect>>',self.mask_selected)
        row=self.frame(right);row.pack(fill='x',padx=12,pady=(8,4))
        self.makebutton(row,'+ Maska',self.add_center_mask,True).pack(side='left',padx=(0,6))
        self.makebutton(row,'Usuń',self.delete_mask).pack(side='left')
        self.heading(right,'Rozmywanie')
        self.mode=tk.StringVar(value='Blur')
        self.strength=tk.IntVar(value=35)
        self.strength_label=tk.StringVar(value='Siła: 35')
        self.label(right,'Efekt',MUTED,9).pack(fill='x',padx=12)
        modebox=ttk.Combobox(right,textvariable=self.mode,values=('Blur','Mosaic'),state='readonly')
        modebox.pack(fill='x',padx=12,pady=(2,7));modebox.bind('<<ComboboxSelected>>',self.property_changed)
        tk.Label(right,textvariable=self.strength_label,bg=PANEL,fg=WHITE,font=('Segoe UI',9),anchor='w').pack(fill='x',padx=12)
        self.blur=tk.Scale(right,from_=1,to=100,orient='horizontal',showvalue=False,variable=self.strength,
                           bg=PANEL,fg=WHITE,troughcolor=GRAY,bd=0,highlightthickness=0,
                           activebackground='#777777',command=self.property_changed)
        self.blur.pack(fill='x',padx=12)
        self.heading(right,'Kształt maski')
        self.shape=tk.StringVar(value='Rectangle')
        shapebox=ttk.Combobox(right,textvariable=self.shape,values=('Rectangle','Ellipse'),state='readonly')
        shapebox.pack(fill='x',padx=12,pady=(0,6));shapebox.bind('<<ComboboxSelected>>',self.property_changed)
        self.oval_width=tk.IntVar(value=100);self.oval_height=tk.IntVar(value=100)
        self.oval_width_label=tk.StringVar(value='Szerokość owalu: 100%')
        self.oval_height_label=tk.StringVar(value='Wysokość owalu: 100%')
        tk.Label(right,textvariable=self.oval_width_label,bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w').pack(fill='x',padx=12)
        self.oval_width_slider=tk.Scale(right,from_=20,to=100,orient='horizontal',showvalue=False,
                               variable=self.oval_width,bg=PANEL,fg=WHITE,troughcolor=GRAY,bd=0,highlightthickness=0,
                               activebackground='#777777',command=self.property_changed)
        self.oval_width_slider.pack(fill='x',padx=12)
        tk.Label(right,textvariable=self.oval_height_label,bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w').pack(fill='x',padx=12)
        self.oval_height_slider=tk.Scale(right,from_=20,to=100,orient='horizontal',showvalue=False,
                                variable=self.oval_height,bg=PANEL,fg=WHITE,troughcolor=GRAY,bd=0,highlightthickness=0,
                                activebackground='#777777',command=self.property_changed)
        self.oval_height_slider.pack(fill='x',padx=12)
        self.enabled=tk.BooleanVar(value=True)
        tk.Checkbutton(right,text='Maska aktywna',variable=self.enabled,command=self.property_changed,
                       bg=PANEL,fg=WHITE,selectcolor='#353535',activebackground=PANEL,
                       activeforeground=WHITE,font=('Segoe UI',9)).pack(anchor='w',padx=12,pady=(2,4))
        ranges=self.frame(right);ranges.pack(fill='x',padx=12,pady=(0,5))
        self.first=tk.StringVar(value='0');self.last=tk.StringVar(value='0')
        for lab,var in [('Od klatki',self.first),('Do klatki',self.last)]:
            col=self.frame(ranges);col.pack(side='left',fill='x',expand=True,padx=(0,6))
            self.label(col,lab,MUTED,9).pack(anchor='w')
            entry=tk.Entry(col,textvariable=var,bg='#303030',fg=WHITE,insertbackground=WHITE,
                           relief='flat',font=('Consolas',10))
            entry.pack(fill='x',pady=(3,0),ipady=4);entry.bind('<Return>',self.range_changed);entry.bind('<FocusOut>',self.range_changed)
        self.heading(right,'Śledzenie')
        self.makebutton(right,'Śledź do przodu',lambda:self.track(False)).pack(fill='x',padx=12,pady=(0,5))
        self.makebutton(right,'Śledź wstecz',lambda:self.track(True)).pack(fill='x',padx=12,pady=(0,5))
        self.makebutton(right,'Wykryj twarze',self.detect_faces).pack(fill='x',padx=12)
        self.heading(right,'Eksport')
        self.audio=tk.BooleanVar(value=True)
        tk.Checkbutton(right,text='Zachowaj dźwięk',variable=self.audio,
                       bg=PANEL,fg=WHITE,selectcolor='#353535',activebackground=PANEL,
                       activeforeground=WHITE,font=('Segoe UI',9)).pack(anchor='w',padx=12,pady=(0,5))
        self.makebutton(right,'Eksportuj MP4',self.export,True).pack(fill='x',padx=12,pady=(0,6))
        self.progress=ttk.Progressbar(right,mode='determinate',maximum=100)
        self.progress.pack(fill='x',padx=12,pady=(0,10))
        self.setup_style()

    def setup_style(self):
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('Treeview',background='#1B1B1B',foreground=WHITE,fieldbackground='#1B1B1B',borderwidth=0,rowheight=24)
        style.map('Treeview',background=[('selected','#555555')],foreground=[('selected',WHITE)])
        style.configure('Treeview.Heading',background=GRAY,foreground=WHITE,font=('Segoe UI',9))
        style.configure('TCombobox',fieldbackground='#333333',background='#333333',foreground=WHITE,
                        arrowcolor=WHITE,selectbackground='#555555',selectforeground=WHITE)
        style.map('TCombobox',fieldbackground=[('readonly','#333333')],foreground=[('readonly',WHITE)])
        style.configure('TProgressbar',background='#777777',troughcolor=GRAY)

    def tile_wheel(self,event):
        self.tiles.xview_scroll(-1 if event.delta>0 else 1,'units')
        return 'break'

    def selected_part(self):
        selection=self.partlist.selection()
        return int(selection[0]) if selection else None

    def pick_tile(self,x,y):
        coordinate=self.tiles.canvasx(x)
        for index,start,end in self.tile_rects:
            if start<=coordinate<end and 0<=y<=112:
                return index, max(0.0,min(1.0,(coordinate-start)/(end-start)))
        return None,None

    def tile_press(self,event):
        index,fraction=self.pick_tile(event.x,event.y)
        if index is None:return
        self.tile_down=(index,self.tiles.canvasx(event.x),event.y)
        self.select_part(index)
        a,b=self.segments[index]
        self.seek(min(b-1,a+round(fraction*(b-a-1))))

    def tile_motion(self,event):
        if not self.tile_down:return
        if abs(self.tiles.canvasx(event.x)-self.tile_down[1])>=9:
            self.tiles.configure(cursor='fleur')

    def tile_release(self,event):
        down=self.tile_down;self.tile_down=None
        self.tiles.configure(cursor='hand2')
        if not down:return
        to,_=self.pick_tile(event.x,event.y)
        source=down[0]
        if to is not None and source!=to and abs(self.tiles.canvasx(event.x)-down[1])>=9:
            item=self.segments.pop(source)
            self.segments.insert(to,item)
            self.refresh_parts(to)

    def select_part(self,index):
        if 0<=index<len(self.segments):
            self._suppress=True
            self.partlist.selection_set(str(index))
            self._suppress=False
            self.draw_tiles()

    def get_segment_thumbnail(self,a,b,width=130,height=72):
        key=(self.path,a,b,width,height)
        if key in self.segment_thumb_cache:return self.segment_thumb_cache[key]
        if self.cap is None:return None
        old=self.pos
        self.cap.set(cv2.CAP_PROP_POS_FRAMES,min(b-1,a+(b-a)//2))
        ok,frame=self.cap.read()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES,old+1)
        if not ok:return None
        frame=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        ih,iw=frame.shape[:2];scale=min(width/iw,height/ih)
        tw=max(1,int(iw*scale));th=max(1,int(ih*scale))
        resized=cv2.resize(frame,(tw,th),interpolation=cv2.INTER_AREA)
        image=ImageTk.PhotoImage(Image.fromarray(resized))
        self.segment_thumb_cache[key]=image
        return image

    def draw_tiles(self):
        if not hasattr(self,'tiles'):return
        canvas=self.tiles;canvas.delete('all')
        self.tile_rects=[];x=7
        selected=self.selected_part()
        self.tile_images=[]
        for index,(a,b) in enumerate(self.segments):
            width=max(128,min(235,int(135+((b-a)/max(self.fps,1))*3)))
            bg='#484848' if selected==index else '#282828'
            outline='#AAAAAA' if selected==index else '#3B3B3B'
            canvas.create_rectangle(x,6,x+width,101,fill=bg,outline=outline,width=2 if selected==index else 1)
            image=self.get_segment_thumbnail(a,b)
            if image:
                self.tile_images.append(image)
                canvas.create_image(x+5,10,anchor='nw',image=image)
            canvas.create_text(x+6,91,anchor='w',fill=WHITE,font=('Segoe UI',9),
                               text=f'{index+1}    {(b-a)/max(self.fps,1):.1f} s')
            self.tile_rects.append((index,x,x+width));x+=width+7
        canvas.configure(scrollregion=(0,0,max(x,canvas.winfo_width()),110))

    def open_video(self):
        path=filedialog.askopenfilename(title='Wczytaj film',filetypes=[('Filmy','*.mp4 *.mov *.avi *.mkv *.m4v'),('Wszystkie','*.*')])
        if path:self.load_path(path)

    def load_path(self,path):
        cap=cv2.VideoCapture(str(path))
        if not cap.isOpened():messagebox.showerror('PROSTE WIDEO','Nie można otworzyć filmu.');return False
        n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps=float(cap.get(cv2.CAP_PROP_FPS))
        if n<1 or fps<=0:
            cap.release();messagebox.showerror('PROSTE WIDEO','Niepoprawna liczba klatek lub FPS.');return False
        self.playing=False
        if self.cap:self.cap.release()
        self.path=str(path);self.cap=cap;self.frames=n;self.fps=fps
        self.width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));self.height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.pos=0;self.masks=[];self.selected=-1;self.segments=[(0,n)];self.segment_thumb_cache.clear()
        self.timeline.configure(to=n-1);self.refresh_masks();self.refresh_parts();self.seek(0)
        self.status_text.set(Path(path).name)
        return True

    def seek(self,idx):
        if self.cap is None:return
        idx=max(0,min(self.frames-1,int(idx)))
        self.pos=idx;self.cap.set(cv2.CAP_PROP_POS_FRAMES,idx)
        ok,fr=self.cap.read()
        if ok:
            self.raw=fr;self.render()
        self._suppress=True;self.timeline.set(idx);self._suppress=False
        self.frame_text.set(f'{idx/self.fps:06.2f} / {self.frames/self.fps:06.2f} s')

    def slider_move(self,val):
        if not self._suppress:self.seek(int(float(val)))

    def toggle_play(self):
        if not self.cap:return
        self.playing=not self.playing
        if self.playing:self.play_mark=time.monotonic()-self.pos/self.fps;self.play_tick()

    def play_tick(self):
        if not self.playing or not self.cap:return
        target=min(self.frames-1,int((time.monotonic()-self.play_mark)*self.fps))
        if target!=self.pos:self.seek(target)
        if target>=self.frames-1:self.playing=False
        else:self.root.after(15,self.play_tick)

    def render(self):
        if not hasattr(self,'raw') or self.raw is None:return
        frame=apply_masks(self.raw,self.masks,self.pos)
        H,W=frame.shape[:2];cw=max(1,self.canvas.winfo_width());ch=max(1,self.canvas.winfo_height())
        scale=min(cw/W,ch/H); dw=max(1,round(W*scale));dh=max(1,round(H*scale))
        ox=(cw-dw)//2;oy=(ch-dh)//2;self.canvas_geometry=(scale,ox,oy)
        rgb=cv2.cvtColor(cv2.resize(frame,(dw,dh),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR),cv2.COLOR_BGR2RGB)
        self.photo=ImageTk.PhotoImage(Image.fromarray(rgb))
        c=self.canvas;c.delete('all');c.create_image(ox,oy,image=self.photo,anchor='nw',tags='video')
        for j,m in enumerate(self.masks):
            if not m.enabled or not m.first<=self.pos<=m.last:continue
            x,y,w,h=m.box_at(self.pos)
            x1=ox+x*scale;y1=oy+y*scale;x2=x1+w*scale;y2=y1+h*scale
            color='#D6D6D6' if j==self.selected else '#888888'
            
            if m.shape=='Ellipse':
                hx=(x2-x1)*m.oval_width/200.0;hy=(y2-y1)*m.oval_height/200.0
                cx=(x1+x2)/2;cy=(y1+y2)/2
                c.create_oval(cx-hx,cy-hy,cx+hx,cy+hy,outline=color,width=2 if j==self.selected else 1,dash=(5,3))
            else:c.create_rectangle(x1,y1,x2,y2,outline=color,width=2 if j==self.selected else 1,dash=(5,3))
            c.create_text(x1+4,y1+4,anchor='nw',text=f'{j+1:02} {m.name}',fill=color,font=('Consolas',10,'bold'))
            if j==self.selected:
                for px,py in ((x1,y1),(x2,y1),(x1,y2),(x2,y2)):
                    c.create_rectangle(px-4,py-4,px+4,py+4,fill='#B6B6B6',outline=INK)
        if self.mouse and self.mouse['kind']=='draw':
            ax,ay=self.mouse['origin'];bx,by=self.mouse['cursor']
            c.create_rectangle(ax,ay,bx,by,outline='#B6B6B6',width=2,dash=(3,2))

    def source_point(self,event):
        scale,ox,oy=self.canvas_geometry
        return (max(0,min(self.width-1,round((event.x-ox)/scale))),
                max(0,min(self.height-1,round((event.y-oy)/scale))))

    def mouse_down(self,e):
        if not self.cap:return
        x,y=self.source_point(e)
        for i in range(len(self.masks)-1,-1,-1):
            m=self.masks[i]
            if not m.enabled or not m.first<=self.pos<=m.last:continue
            bx,by,bw,bh=m.box_at(self.pos);tol=max(5,int(8/max(0.01,self.canvas_geometry[0])))
            if bx-tol<=x<=bx+bw+tol and by-tol<=y<=by+bh+tol:
                self.select_mask(i)
                corner=None
                for name,px,py in [('nw',bx,by),('ne',bx+bw,by),('sw',bx,by+bh),('se',bx+bw,by+bh)]:
                    if abs(px-x)<=tol and abs(py-y)<=tol:corner=name;break
                self.mouse={'kind':'resize' if corner else 'move','corner':corner,
                            'origin':(x,y),'source_box':(bx,by,bw,bh),'mask':i,'changed':False}
                return
        self.mouse={'kind':'draw','origin':(e.x,e.y),'cursor':(e.x,e.y)}

    def mouse_move(self,e):
        if self.mouse is None:return
        drag=self.mouse
        if drag['kind']=='draw':drag['cursor']=(e.x,e.y);self.render();return
        x,y=self.source_point(e);startx,starty=drag['origin'];bx,by,bw,bh=drag['source_box']
        dx=x-startx;dy=y-starty
        if drag['kind']=='move':
            box=clamp_box((bx+dx,by+dy,bw,bh),self.width,self.height)
        else:
            corner=drag['corner'];x0=bx+dx if 'w' in corner else bx
            y0=by+dy if 'n' in corner else by
            x1=bx+bw+dx if 'e' in corner else bx+bw
            y1=by+bh+dy if 's' in corner else by+bh
            x0,x1=sorted((x0,x1));y0,y1=sorted((y0,y1))
            box=clamp_box((x0,y0,max(8,x1-x0),max(8,y1-y0)),self.width,self.height)
        self.masks[drag['mask']].keys[self.pos]=box;drag['changed']=True
        self.render()

    def mouse_up(self,e):
        if self.mouse is None:return
        drag=self.mouse;self.mouse=None
        if drag['kind']=='draw':
            a,b=self.source_point(type('Point',(),{'x':drag['origin'][0],'y':drag['origin'][1]})())
            c,d=self.source_point(e)
            x=min(a,c);y=min(b,d);w=abs(a-c);h=abs(b-d)
            if w>=10 and h>=10:self.new_mask((x,y,w,h))
        elif drag.get('changed'):
            self.status_text.set(f'Korekta: {self.pos+1}')
        self.render()

    def new_mask(self,box):
        name=f'MASKA {len(self.masks)+1:02}'
        m=Mask(name,tuple(box),first=self.pos,last=self.frames-1)
        m.keys[self.pos]=tuple(box)
        self.masks.append(m);self.refresh_masks();self.select_mask(len(self.masks)-1);self.render()

    def add_center_mask(self):
        if self.cap is None:return
        w=max(30,self.width//6);h=max(30,self.height//6)
        self.new_mask(((self.width-w)//2,(self.height-h)//2,w,h))

    def delete_mask(self):
        if self.selected<0:return
        self.masks.pop(self.selected);self.selected=-1;self.refresh_masks();self.render()

    def refresh_masks(self):
        self.masklist.delete(0,'end')
        for m in self.masks:
            self.masklist.insert('end',f'{m.name}  ·  {m.strength}')
        if 0<=self.selected<len(self.masks):self.masklist.selection_set(self.selected)

    def mask_selected(self,e):
        if self._suppress:return
        sel=self.masklist.curselection()
        if sel:self.select_mask(sel[0])

    def select_mask(self,idx):
        if not 0<=idx<len(self.masks):return
        self.selected=idx;m=self.masks[idx]
        self._suppress=True
        self.masklist.selection_clear(0,'end');self.masklist.selection_set(idx)
        self.strength.set(m.strength);self.strength_label.set(f'Siła: {m.strength}')
        self.shape.set(m.shape);self.oval_width.set(m.oval_width);self.oval_height.set(m.oval_height)
        self.oval_width_label.set(f'Szerokość owalu: {m.oval_width}%')
        self.oval_height_label.set(f'Wysokość owalu: {m.oval_height}%')
        self.mode.set(m.mode);self.enabled.set(m.enabled)
        self.first.set(str(m.first+1));self.last.set(str(m.last+1))
        self._suppress=False;self.render()

    def property_changed(self,*args):
        if self._suppress or self.selected<0:return
        m=self.masks[self.selected];m.strength=self.strength.get();m.mode=self.mode.get();m.enabled=self.enabled.get()
        m.shape=self.shape.get();m.oval_width=self.oval_width.get();m.oval_height=self.oval_height.get()
        self.strength_label.set(f'Siła: {m.strength}')
        self.oval_width_label.set(f'Szerokość owalu: {m.oval_width}%')
        self.oval_height_label.set(f'Wysokość owalu: {m.oval_height}%')
        self.refresh_masks();self.render()

    def range_changed(self,e=None):
        if self._suppress or self.selected<0:return
        try:
            first=max(1,min(self.frames,int(self.first.get())))-1
            last=max(first+1,min(self.frames,int(self.last.get())))-1
        except ValueError:
            self.select_mask(self.selected);return
        m=self.masks[self.selected];m.first=first;m.last=last;self.select_mask(self.selected)

    def add_key(self):
        if self.selected<0:return
        m=self.masks[self.selected];m.keys[self.pos]=m.box_at(self.pos)
        self.status_text.set(f'Klatka kluczowa: {self.pos+1}')
        self.render()

    def detect_faces(self):
        if self.cap is None:return
        cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
        faces=cascade.detectMultiScale(cv2.cvtColor(self.raw,cv2.COLOR_BGR2GRAY),scaleFactor=1.1,minNeighbors=5)
        for x,y,w,h in faces:self.new_mask((int(x),int(y),int(w),int(h)))
        self.status_text.set(f'Twarze: {len(faces)}')

    def track(self,reverse):
        if self.selected<0 or self.cap is None or self.task:return
        mask_i=self.selected;mask=copy.deepcopy(self.masks[mask_i]);begin=self.pos
        end=mask.first if reverse else min(mask.last,self.frames-1)
        if begin==end:self.status_text.set('Wybierz inną klatkę');return
        def worker():
            try:
                result=track_range(self.path,mask,begin,end,callback=lambda p:self.events.put(('progress',p)))
                self.events.put(('track_done',(mask_i,result)))
            except Exception as exc:self.events.put(('error',str(exc)))
        self.task=threading.Thread(target=worker,daemon=True);self.task.start()
        self.status_text.set('Śledzenie...')

    def fmt(self,idx):return f'{idx/self.fps:.2f}s'

    def refresh_parts(self,selected=None):
        self._suppress=True
        self.partlist.delete(*self.partlist.get_children())
        for j,(a,b) in enumerate(self.segments):
            self.partlist.insert('', 'end',iid=str(j),values=(f'{j+1:02}',self.fmt(a),self.fmt(b),self.fmt(b-a)))
        if selected is not None and 0<=selected<len(self.segments):self.partlist.selection_set(str(selected))
        self._suppress=False
        self.draw_tiles()

    def part_selected(self,e):
        if self._suppress:return
        sel=self.partlist.selection()
        if sel:
            self.draw_tiles()
            self.seek(self.segments[int(sel[0])][0])

    def cut_here(self):
        if self.cap is None:return
        prev=len(self.segments);new=split_segment(self.segments,self.pos)
        self.segments=new;self.refresh_parts()
        if len(new)>prev:self.status_text.set(f'Cięcie: {self.pos+1}')
        else:self.status_text.set('Cięcie poza fragmentem')

    def move_part(self,step):
        sel=self.partlist.selection()
        if not sel:return
        j=int(sel[0]);k=j+step
        if not 0<=k<len(self.segments):return
        self.segments[j],self.segments[k]=self.segments[k],self.segments[j]
        self.refresh_parts(k)

    def delete_part(self):
        sel=self.partlist.selection()
        if not sel:return
        j=int(sel[0]);self.segments.pop(j);self.refresh_parts(min(j,len(self.segments)-1))


    def save_project(self):
        if self.cap is None:return
        path=filedialog.asksaveasfilename(title='Zapisz projekt',defaultextension='.prostewideo.json',
             filetypes=[('Projekt PROSTE WIDEO','*.prostewideo.json')],initialfile=Path(self.path).stem+'.prostewideo.json')
        if not path:return
        payload={'format':'PROSTE-WIDEO-1','source':self.path,'segments':self.segments,
                 'masks':[{'name':m.name,'base':m.base,'strength':m.strength,'mode':m.mode,
                           'shape':m.shape,'oval_width':m.oval_width,'oval_height':m.oval_height,
                           'enabled':m.enabled,'first':m.first,'last':m.last,
                           'keys':{str(k):v for k,v in m.keys.items()},
                           'tracked':{str(k):v for k,v in m.tracked.items()}} for m in self.masks]}
        try:
            with open(path,'w',encoding='utf-8') as f:json.dump(payload,f,ensure_ascii=False,indent=2)
            self.status_text.set('Zapisano: '+Path(path).name)
        except Exception as exc:messagebox.showerror('PROSTE WIDEO',str(exc))

    def open_project(self):
        path=filedialog.askopenfilename(title='Otwórz projekt',
              filetypes=[('Projekt PROSTE WIDEO','*.prostewideo.json'),('Starszy projekt','*.protovid.json'),('JSON','*.json')])
        if not path:return
        try:
            with open(path,encoding='utf-8') as f:p=json.load(f)
            if p.get('format') not in ('PROSTE-WIDEO-1','PROTOVID-1'):raise ValueError('Nieobsługiwany format projektu.')
            source=p['source']
            if not Path(source).exists():
                source=filedialog.askopenfilename(title='Wskaż film źródłowy projektu')
                if not source:return
            if not self.load_path(source):return
            segments=[tuple(map(int,seg)) for seg in p['segments']]
            if any(a<0 or b>self.frames or a>=b for a,b in segments):
                raise ValueError('Projekt zawiera niepoprawne przedziały klatek.')
            masks=[]
            for v in p['masks']:
                m=Mask(str(v['name']),tuple(v['base']),strength=int(v['strength']),mode=v['mode'],
                       enabled=bool(v['enabled']),first=int(v['first']),last=int(v['last']),
                       shape=v.get('shape','Rectangle'),oval_width=int(v.get('oval_width',100)),
                       oval_height=int(v.get('oval_height',100)))
                m.keys={int(k):tuple(box) for k,box in v['keys'].items()}
                m.tracked={int(k):tuple(box) for k,box in v['tracked'].items()}
                masks.append(m)
            self.masks=masks;self.segments=segments;self.refresh_masks();self.refresh_parts();self.seek(0)
            self.status_text.set('Otworzono: '+Path(path).name)
        except Exception as exc:messagebox.showerror('PROSTE WIDEO',f'Nie można otworzyć projektu:\n{exc}')

    def export(self):
        if self.cap is None or self.task:return
        if not self.segments:messagebox.showwarning('PROSTE WIDEO','Nie ma fragmentów do wyeksportowania.');return
        target=filedialog.asksaveasfilename(title='Zapisz film',defaultextension='.mp4',
                 filetypes=[('Film MP4','*.mp4')],initialfile=Path(self.path).stem+'_PROSTE_WIDEO.mp4')
        if not target:return
        if Path(target).resolve()==Path(self.path).resolve():
            messagebox.showwarning('PROSTE WIDEO','Wybierz inną nazwę niż plik źródłowy.');return
        snapshot=copy.deepcopy(self.masks);parts=list(self.segments);audio=self.audio.get()
        self.progress['value']=0
        def worker():
            try:
                result=export_video(self.path,target,snapshot,parts,keep_audio=audio,
                                    callback=lambda n:self.events.put(('progress',n)))
                self.events.put(('export_done',result))
            except Exception as exc:self.events.put(('error',str(exc)))
        self.task=threading.Thread(target=worker,daemon=True);self.task.start()
        self.status_text.set('Eksport...')

    def poll_events(self):
        try:
            while True:
                typ,payload=self.events.get_nowait()
                if typ=='progress':self.progress['value']=payload
                elif typ=='track_done':
                    i,boxes=payload
                    if 0<=i<len(self.masks):self.masks[i].tracked.update(boxes)
                    self.task=None;self.render();self.status_text.set('Śledzenie gotowe')
                elif typ=='export_done':
                    self.task=None;self.status_text.set('Eksport gotowy')
                    messagebox.showinfo('PROSTE WIDEO',f'Film zapisany:\n{payload["path"]}\n\nKlatki: {payload["frames"]}\nDźwięk: {"TAK" if payload["audio"] else "NIE"}')
                elif typ=='error':
                    self.task=None;self.status_text.set('Błąd')
                    messagebox.showerror('PROSTE WIDEO',payload)
        except queue.Empty:pass
        self.root.after(60,self.poll_events)

    def close(self):
        if self.task and self.task.is_alive():
            messagebox.showwarning('PROSTE WIDEO','Trwa przetwarzanie. Zakończ je przed zamknięciem.');return
        self.playing=False
        if self.cap:self.cap.release()
        self.root.destroy()


def main():
    root=tk.Tk();ProsteWideo(root);root.mainloop()

if __name__=='__main__':main()
