#!/usr/bin/env python

# $Id$

import sys, os
import signal, time
import string

from gdb import Gdb
from getline import getline

class PyGdb(Gdb):
    def dgdb_command(self, args):
        print args
        r=self.gdb_command(args)
        print r
        return r
        
    def __init__(self, args):
        Gdb.__init__(self,['python']+args)
        pd=os.environ.get("PYTHON_DIR",None)
        if pd:
            pd=pd+"/Python-1.5.2"
            self.gdb_command("dir %s/Python" % pd)
            #self.gdb_command("dir %s/Objects" % pd)
            #self.gdb_command("dir %s/Modules" % pd)
        self.gdb_command("b ceval.c:1539") #set_lineno
        self.breakpoints = {}
        self.breakpoint_number = 0
        self.trace = 0
        self.interrupted = 0
        self.break_next_line = 0
        self.cont = 0
        self.filename = None
        self.line = None
        self.pygdb_prompt = "(pygdb) "
        self.gdb_mode = 0
        self.prompt = self.pygdb_prompt
        
        self.help = ["Commands:",
                     " b: set breakpoint at line or in function",
                     " c: continue",
                     " d: delete breakpoint (with no arg, delete all breakpoints)",
                     " h|?: help",
                     " i: info (lists breakpoints)",
                     " l: list source code",
                     " q: quit",
                     " s: single-step",
                     " t: toggle tracing",
                     " w: where (print backtrace)",
                     " gdb <gdb-command>:  passes <command> to underlying gdb",
                     ]

    def set_breakpoint_at_file_line(self,file,line):
        if file[-3:] != '.py':
            file=file+'.py'
        if (file,line) not in self.breakpoints.keys():
            self.breakpoint_number = self.breakpoint_number+1
            self.breakpoints[(file,line)]=self.breakpoint_number
            return ['Breakpoint %d at %s:%d' % (
                self.breakpoint_number,file,line)]
        else:
            return ['Already have a breakpoint at %s:%d' % (
                file,line)]
        
    def set_breakpoint(self,expr):
        usage = 'Usage: b[reak] file:line|function'
        if len(string.split(expr))>1:
            return [usage]
        colon = string.find(expr,':')
        if colon>0:
            file = expr[:colon]
            try:
                line = string.atoi(expr[colon+1:])
            except ValueError:
                return [usage]

            return self.set_breakpoint_at_file_line(file,line)
            
        else:
            try:
                line = string.atoi(expr)
                if not self.filename:
                    return ["No default filename"]
                file = self.filename
                return self.set_breakpoint_at_file_line(file,line)
            except ValueError:
                func = expr
                if func not in self.breakpoints.keys():
                    self.breakpoint_number = self.breakpoint_number+1
                    self.breakpoints[func] = self.breakpoint_number
                    return ['Breakpoint %d in %s' % (self.breakpoint_number,
                                                     func)]
                else:
                    return ['Already have a breakpoint in %s' % func]
            
            
    def delete_breakpoint(self,number):
        if number in self.breakpoints.values():
            for k in self.breakpoints.keys():
                if self.breakpoints[k]==number:
                    del self.breakpoints[k]
                    break
            return 1
        else:
            return None

    def delete_all_breakpoints(self):
        self.breakpoints={}
        self.breakpoint_number = 0

    def c_numeric_expr(self, expr):
        response = self.gdb_command("print "+expr)
        r = string.split(response[0])
        try:
            return eval(r[-1])
        except:
            return -1

    def c_string_expr(self, expr):
        response = self.gdb_command("print (char*)( ( (PyStringObject*) %s)->ob_sval)" % expr)
        r = string.split(response[0])
        return string.join(r[3:])[1:-1]

    def backtrace(self):
        if self.at_gdb_breakpoint() != 1:
##            return ['Not at a Python source line, printing C backtrace'] + \
##                   self.gdb_command('where')
            self.gdb_command("cont")
        
        frame_expr = 'f'
        ret = []
        depth  = 0
        while 1:
            file = self.c_string_expr(frame_expr+'->f_code->co_filename')
            line = self.c_numeric_expr(frame_expr+'->f_lineno')
            if depth==0:
                self.line = line
                self.filename = file
            func = self.c_string_expr(frame_expr+'->f_code->co_name')
            ret.append("#%d %s at %s:%d" % (depth,func,file,line))
            depth=depth+1
            frame_expr = frame_expr + '->f_back'
            x = self.c_numeric_expr(frame_expr)
            if not x:
                break
        return ret

    def list(self):
        if not self.filename:
            return ['No current source file']
        if not self.line:
            self.line = 5
        ret = []
        for x in range(self.line-5, self.line+5):
            l = getline(self.filename,x)
            if l:
                ret.append('%d %s' % (x,l))
        self.line = self.line + 10
        return ret
    
    def command(self,cmd):
        if self.gdb_mode:
            if cmd[:2]== 'py':
                self.gdb_mode = 0
                self.prompt = self.pygdb_prompt
                return ['Entering pygdb mode']
            else:
                return self.dgdb_command(cmd)

        tok = string.split(cmd)
        ntok = len(tok)
        cmd_chr = tok[0][0]
        if cmd_chr == 'b':
            return self.set_breakpoint(tok[1])
        elif cmd_chr == 'w':
            return self.backtrace()
        elif cmd_chr == 't':
            self.trace = self.trace+1
            if self.trace>2: self.trace=0
            return ['trace %s' % self.trace]
        elif cmd_chr == 'd':
            if ntok==1:
                self.delete_all_breakpoints()
                return [ 'Deleted all breakpoints']
            else:
                try:
                    bp = string.atoi(tok[1])
                    if self.delete_breakpoint(bp):
                        return ['Deleted breakpoint %d' %bp]
                    else:
                        return ['No breakpoint %d' % bp]
                except ValueError:
                    return ['Usage: d[elete] [breakpoint_number]']
        elif cmd_chr == 'i':
            bps = self.breakpoints.values()
            if not bps:
                return ['No breakpoints set']
            else:
                ret = ['Breakpoints:']
            bps.sort()
            for bp in bps:
                for k in self.breakpoints.keys():
                    if self.breakpoints[k]==bp:
                        if type(k)==type(()):
                            ret.append(" %d at %s:%d" % (bp,k[0],k[1]))
                        else: 
                            ret.append(" %d in %s" % (bp,k))
            return ret
        elif cmd_chr == 'q':
            sys.exit(0)
        elif cmd_chr == 's':
            self.break_next_line = 1
            self.cont = 1
        elif cmd_chr == 'l':
            return self.list()
        elif cmd_chr == 'c':
            return self.gdb_command(cmd)
        elif cmd_chr in 'h?':
            return self.help
        elif cmd[:3]=='gdb':
            if ntok>1:
                return self.gdb_command(cmd[4:])
            else:
                self.gdb_mode = 1
                self.prompt = self.gdb_prompt
                return ['Entering gdb mode']
            
        else:
            return ['Unrecognized command %s' % cmd]
        

if __name__ == "__main__":
    try:
        pid = string.atoi(sys.argv[1])
    except:
        pid = None

    if not pid:
        print "Usage: %s pid" % sys.argv[0]
        sys.exit(-1)

    try:
        import readline
    except ImportError:
        pass
        
    pygdb = PyGdb(sys.argv[1:])
    welcome = pygdb.get_response()

    def print_response(response):
        if not response:
            return
        for r in response:
            if r != pygdb.gdb_prompt:
                print r

    while 1:
        try:
            while 1:
                if pygdb.cont:
                    cmd = 'c'
                else:
                    cmd = raw_input(pygdb.prompt)
                    
                if  not cmd and not pygdb.allow_default_repeat:
                    continue

                response = pygdb.command(cmd)
                if pygdb.at_gdb_breakpoint()==1:
                    pygdb.cont = 0
                    pygdb.line = pygdb.c_numeric_expr('oparg')
                    pygdb.filename = pygdb.c_string_expr('co->co_filename')
                    basename = os.path.split(pygdb.filename)[-1]
                    func = pygdb.c_string_expr('co->co_name')
                    bp1 = pygdb.breakpoints.get((basename,pygdb.line))
                    bp2 = pygdb.breakpoints.get(func)
                    bp = bp1 or bp2
                    if bp:
                        print "Breakpoint %d, %s at %s:%d" % \
                              (bp,func,pygdb.filename,pygdb.line)
                        pygdb.cont = 0
                    elif pygdb.break_next_line:
                        print "%s at %s:%d" % (func,pygdb.filename,pygdb.line)
                        pygdb.break_next_line=0
                        pygdb.cont = 0
                    elif pygdb.trace==1:
                        print "%s at %s:%d" %(func,pygdb.filename,pygdb.line)
                    elif pygdb.trace==2:
                        f=string.split(pygdb.filename,'/')
                        if f: f=f[-1]
                        else: f="?"
                        print "%s:%d  %s"%(f,pygdb.line,getline(pygdb.filename,pygdb.line))
                        pygdb.cont = 1
                    else: pygdb.cont = 1
        
                else:
                    if not pygdb.interrupted:
                        print_response(response)
                    pygdb.interrupted = 0
        except KeyboardInterrupt:
            if pid:
                os.kill(pid,signal.SIGINT)
                print "*Break* at",
            pygdb.cont = 1
            pygdb.interrupted = 1
            response = pygdb.get_response()
            pygdb.break_next_line = 1
            
