#
# Module Orange Interactions
# --------------------------
#
# CVS Status: $Id$
#
# Author: Aleks Jakulin (jakulin@acm.org)
#
# Purpose: Analysis of dependencies between attributes given the class.
#          3-WAY INTERACTIONS
#
# Project initiated on 2003/05/08
#
# ChangeLog:
#   - 2003/05/09:
#       fixed a problem with domains that need no preprocessing
#       fixed the decimal point printing problem
#       added the support for dissimilarity matrix, used for attribute clustering
#   - 2003/05/10:
#       fixed a problem with negative percentages of less than a percent
#   - 2003/05/12:
#       separated the 'prepare' function
#   - 2003/09/18:
#       added support for cluster coloring
#       cleaned up backwards-incompatible changes (grrr) (color changes, discData)
#       added color-coded dissimilarity matrix export
#   - 2004/01/31:
#       removed adhoc stats-gathering code in favor of the orngContingency module
#       added p-value estimates

import orange
import orngContingency
import warnings, math, string, copy

def _nicefloat(f,sig):
    # pretty-float formatter
    i = int(f)
    s = '%1.0f'%f
    n = sig-len('%d'%abs(f)) # how many digits is the integer part
    if n > 0:
        # we can put a few decimals at the end
        fp = abs(f)-abs(i)
        s = ''
        if f < 0:
            s += '-'
        s += '%d'%abs(i) + ('%f'%fp)[1:2+n]
        
    return s



class InteractionMatrix:
    def _prepare(self, t):
        # prepares an Orange table so that it doesn't contain continuous
        # attributes or missing values

        ### DISCRETIZE VARIABLES ###
        
        newatt = []
        oldatt = []
        entroD = orange.EntropyDiscretization()
        equiD = orange.EquiNDiscretization(numberOfIntervals = 2)
        for i in t.domain.attributes:
            if i.varType == 2:
                d = entroD(i,t)
                if len(d.values) < 2:
                    # prevent discretization into a single value
                    d = equiD(i,t)
                    d.name = 'E'+d.name
                warnings.warn('Discretizing %s into %s with %d values.'%(i.name,d.name,len(d.values)))
                newatt.append(d)
            else:
                oldatt.append(i)
        if len(newatt) > 0:
            t = t.select(oldatt+newatt+[t.domain.classVar])
        
        ### FIX MISSING VALUES ###
            
        special_attributes = []
        all_attributes = [i for i in t.domain.attributes]+[t.domain.classVar]
        for i in range(len(all_attributes)):
            for j in t:
                if j[i].isSpecial():
                    special_attributes.append(i)
                    break
        # create new attributes
        if len(special_attributes) > 0:
            # prepare attributes
            newatts = []
            for i in range(len(all_attributes)):
                old = all_attributes[i]
                if i in special_attributes:
                    oldv = [v for v in old.values]
                    assert('.' not in oldv)
                    new = orange.EnumVariable(name='M_'+old.name, values=oldv+['.'])
                    warnings.warn('Removing special values from %s into %s.'%(old.name,new.name))
                    newatts.append(new)
                else:
                    newatts.append(old)
            # convert table
            exs = []
            newd = orange.Domain(newatts)
            for ex in t:
                nex = []
                for i in range(len(newatts)):
                    if ex[i].isSpecial():
                        v = newatts[i]('.')
                    else:
                        v = newatts[i](int(ex[i]))
                    nex.append(v)
                exs.append(orange.Example(newd,nex))
            t = orange.ExampleTable(exs)
        return t
        
    def __init__(self, t, save_data=1, interactions_too = 1, dependencies_too=0, prepare=1, pvalues = 0, iterative_scaling=0):
        if prepare:
            t = self._prepare(t)
        if save_data:
            self.discData = t   # save the discretized data

        ### PREPARE INDIVIDUAL ATTRIBUTES ###

        # Attribute Preparation
        NA = len(t.domain.attributes)
        
        self.names = []
        self.gains = []
        self.freqs = []
        self.way2 = {}
        self.way3 = {}
        self.ig = []
        self.list = []
        self.abslist = []
        self.plist = []
        self.plut = {}
        self.ents = {}
        self.corr = {}
        for i in range(NA):
            atc = orngContingency.get2Int(t,t.domain.attributes[i],t.domain.classVar)
            gai = atc.InteractionInformation()
            self.gains.append(gai)
            self.corr[(i,-1)] = gai
            self.ents[(i,)] = orngContingency.Entropy(atc.a)
            self.way2[(i,-1,)] = atc
            self.ents[(i,-1)] = orngContingency.Entropy(atc.m)
            # fix the name
            st = '%s'%t.domain.attributes[i].name # copy
            self.names.append(st)
            if pvalues:
                pv = orngContingency.getPvalue(gai,atc)
                self.plist.append((pv,(gai,i,-1)))
                self.plut[(i,-1)] = pv
                #print "%s\t%f\t%f\t%d"%(st,pv,gai,atc.total)
            line = []
            for j in range(i):
                if dependencies_too:
                    c = orngContingency.get2Int(t,t.domain.attributes[j],t.domain.attributes[i])
                    self.way2[(j,i,)] = c
                    gai = c.InteractionInformation()
                    self.ents[(j,i,)] = orngContingency.Entropy(c.m)
                    self.corr[(j,i,)] = gai
                    if pvalues:
                        pv = orngContingency.getPvalue(gai,c)
                        self.plist.append((pv,(gai,j,i)))
                        self.plut[(j,i)] = pv
                if interactions_too:
                    c = orngContingency.get3Int(t,t.domain.attributes[j],t.domain.attributes[i],t.domain.classVar)
                    igv = c.InteractionInformation()
                    line.append(igv)
                    self.list.append((igv,(igv,j,i)))
                    self.abslist.append((abs(igv),(igv,j,i)))
                    if pvalues:
                        if iterative_scaling:
                            div = c.IPF()
                        else:
                            div = c.KSA()[0]
                        pv = orngContingency.getPvalue(div,c)
                        #print "%s-%s\t%f\t%f\t%d"%(c.names[0],c.names[1],pv,igv,c.total)
                        self.plist.append((pv,(igv,j,i,-1)))
                        self.plut[(j,i,-1)] = pv
            self.ig.append(line)
        self.entropy = orngContingency.Entropy(atc.b)
        self.ents[(-1,)] = self.entropy
        self.list.sort()
        self.abslist.sort()
        self.plist.sort()

        self.attlist = []
        for i in range(NA):
            self.attlist.append((self.gains[i],i))
        self.attlist.sort()

    def dump(self):
        NA = len(self.names)
        for j in range(1,NA):
            for i in range(j):
                t = '%s+%s'%(self.names[i],self.names[j])
                print "%30s\t%2.4f\t%2.4f\t%2.4f\t%2.4f\t%2.4f"%(t,self.igain[(i,j)],self.corr[(i,j)],self.igain[(i,j)]+self.corr[(i,j)],self.gains[i],self.gains[j])

    def exportGraph(self, f, absolute_int=10, positive_int = 0, negative_int = 0, best_attributes = 0, print_bits = 1, black_white = 0, significant_digits = 2, postscript = 1, pretty_names = 1, url = 0, widget_coloring=1, pcutoff = 1):
        NA = len(self.names)

        ### SELECTION OF INTERACTIONS AND ATTRIBUTES ###

        # prevent crashes
        best_attributes = min(best_attributes,len(self.attlist))
        positive_int = min(positive_int,len(self.list))
        absolute_int = min(absolute_int,len(self.list))
        negative_int = min(negative_int,len(self.list))
        
        # select the top interactions
        ins = []
        if positive_int > 0:
            ins += self.list[-positive_int:]
        ins += self.list[:negative_int]
        if absolute_int > 0:
            ins += self.abslist[-absolute_int:]

        # pick best few attributes
        atts = []
        if best_attributes > 0:
            atts += [i for (x,i) in self.attlist[-best_attributes:]]

        # disregard the insignificant attributes, interactions
        if len(self.plist) > 0 and pcutoff < 1:
            # attributes
            oats = atts
            atts = []
            for i in oats:
                if self.plut[(i,-1)] < pcutoff:
                    atts.append(i)
            # interactions
            oins = ins
            ins = []
            for y in oins:
                (ig,i,j) = y[1] 
                if self.plut[(i,j,-1)] < pcutoff:
                    ins.append(y)

        ints = []
        max_igain = -1e6
        min_gain = 1e6 # lowest information gain of involved attributes
        # remove duplicates and sorting keys
        for (x,v) in ins:
            if v not in ints:
                ints.append(v)
                # add to attribute list
                (ig,i,j) = v
                max_igain = max(abs(ig),max_igain)
                for x in [i,j]:
                    if x not in atts:
                        atts.append(x)
                        min_gain = min(min_gain,self.gains[x])

        # fill-in the attribute list with all possibly more important attributes
        ## todo

        ### NODE DRAWING ###

        # output the attributes
        f.write("digraph G {\n")

        if print_bits:
            shap = 'record'
        else:
            shap = 'box'

        for i in atts:
            t = '%s'%self.names[i]
            if pretty_names:
                t = string.replace(t,"ED_","")
                t = string.replace(t,"D_","")
                t = string.replace(t,"M_","")
                t = string.replace(t," ","\\n")
                t = string.replace(t,"-","\\n")
                t = string.replace(t,"_","\\n")
            if print_bits:
                r = self.gains[i]*100.0/self.entropy
                if len(self.plist) > 0 and pcutoff < 1:
                    t = "{%s|{%s%% | P\<%.3f}}"%(t,_nicefloat(r,significant_digits),self.plut[(i,-1)])
                else:
                    t = "{%s|%s%%}"%(t,_nicefloat(r,significant_digits))
            if not url:
                f.write("\tnode [ shape=%s, label = \"%s\"] %d;\n"%(shap,t,i))
            else:
                f.write("\tnode [ shape=%s, URL = \"%d\", label = \"%s\"] %d;\n"%(shap,i,t,i))
            
        ### EDGE DRAWING ###

        for (ig,i,j) in ints:
            perc = int(abs(ig)*100.0/max(max_igain,self.attlist[-1][0])+0.5)

            if self.entropy > 1e-6:
                mc = _nicefloat(100.0*ig/self.entropy,significant_digits)+"%"
            else:
                mc = _nicefloat(0.0,significant_digits)                
            if len(self.plist) > 0 and pcutoff < 1:
                mc += "\\nP\<%.3f"%self.plut[(i,j,-1)]
            if postscript:
                style = "style=\"setlinewidth(%d)\","%(abs(perc)/30+1)
            else:
                style = ''
            if black_white:
                color = 'black'
                if ig > 0:
                    dir = "both"
                else:
                    style = 'style=dashed,'
                    dir = 'none'
            else:            
                if ig > 0:
                    if widget_coloring:
                        color = "green"
                    else:
                        color = '"0.0 %f 0.9"'%(0.3+0.7*perc/100.0) # adjust saturation
                    dir = "both"
                else:
                    if widget_coloring:
                        color = "red"
                    else:
                        color = '"0.5 %f 0.9"'%(0.3+0.7*perc/100.0) # adjust saturation
                    dir = 'none'
            if not url:
                f.write("\t%d -> %d [dir=%s,%scolor=%s,label=\"%s\",weight=%d];\n"%(i,j,dir,style,color,mc,(perc/30+1)))
            else:
                f.write("\t%d -> %d [URL=\"%d-%d\",dir=%s,%scolor=%s,label=\"%s%%\",weight=%d];\n"%(i,j,min(i,j),max(i,j),dir,style,color,mc,(perc/30+1)))

        f.write("}\n")
        
    def exportDissimilarityMatrix(self, truncation = 1000, pretty_names = 1, print_bits = 0, significant_digits = 2, show_gains = 1, color_coding = 0, color_gains = 0, jaccard=0, noclass=0):
        NA = len(self.names)

        ### BEAUTIFY THE LABELS ###

        labels = []
        maxgain = max(self.gains)
        for i in range(NA):
            t = '%s'%self.names[i]
            if pretty_names:
                t = string.replace(t,"ED_","")
                t = string.replace(t,"D_","")
                t = string.replace(t,"M_","")
            r = self.gains[i]
            if print_bits:
                if self.entropy > 1e-6:
                    t = "%s (%s%%)"%(t,_nicefloat(r*100.0/self.entropy,significant_digits))
                else:
                    t = "%s (0%%)"%(t)
            if show_gains: # a bar indicating the feature importance
                if maxgain > 1e-6:
                    t += ' '+'*'*int(8.0*r/maxgain+0.5)
            labels.append(t)

        ### CREATE THE DISSIMILARITY MATRIX ###
        
        if jaccard:
            # create the lookup of 3-entropies
            ent3 = {}
            maxx = 1e-6
            for i in range(1,NA):
                for j in range(i):
                    if noclass:
                        e = self.ents[(j,i)]
                    else:
                        e = self.ents[(j,i)]+self.ents[(j,-1)]+self.ents[(i,-1)]
                        e -= self.ents[(i,)]+self.ents[(j,)]+self.ents[(-1,)]
                        e -= self.ig[i][j]
                    ent3[(i,j)] = e
                    if e > 1e-6:
                        e = abs(self.ig[i][j])/e
                    else:
                        e = 0.0
                    maxx = max(maxx,e)
            # check the information gains...
            if color_gains:
                for i in range(NA):
                    e = self.gains[i]
                    if self.ents[(i,-1)] > 1e-6:
                        e /= self.ents[(i,-1)]
                    else:
                        e = 0.0
                    ent3[(i,)] = e 
                    maxx = max(maxx,e)
        else:
            maxx = self.abslist[-1][0]
            if color_gains:
                maxx = max(maxx,self.attlist[-1][0])
        if color_gains:
            if maxx > 1e-6:
                cgains = [0.5*(1-i/maxx) for i in self.gains]
            else:
                cgains = [0.0 for i in self.gains]                
        diss = []        
        for i in range(1,NA):
            newl = []
            for j in range(i):
                d = self.ig[i][j]
                if jaccard:
                    if ent3[(i,j)] > 1e-6:
                        d /= ent3[(i,j)]
                    else:
                        d = 0.0
                if color_coding:
                    if maxx > 1e-6:
                        if maxx > 1e-6:
                            t = 0.5*(1-d/maxx)
                        else:
                            t = 0.0
                    else:
                        t = 0
                else:
                    # transform the IG into a distance
                    ad = abs(d)
                    if ad*truncation > 1:
                        t = 1.0 / ad
                    else:
                        t = truncation
                newl.append(t)
            diss.append(newl)

        if color_gains:
            return (diss,labels,cgains)
        else:
            return (diss,labels)

    def getClusterAverages(self, clust):
        #assert(len(self.attlist) == clust.n)
        # get the max value
        #d = max(self.attlist[-1][0],self.abslist[-1][0])
        d = self.abslist[-1][0]
        # prepare a lookup
        LUT = {}
        for (ig,(igv,i,j)) in self.list:
            LUT[i,j] = igv
            LUT[j,i] = igv

        cols = []
        merges = []
        for i in range(clust.n):
            merges.append((0.0,[clust.n-i-1]))
        merges.append("sentry")
        p = clust.n
        for i in range(clust.n-1):
            a = merges[p+clust.merging[i][0]] # cluster 1
            b = merges[p+clust.merging[i][1]] # cluster 2
            na = len(a[1])
            nb = len(b[1])
            # compute cross-average
            sum = 0.0
            for x in a[1]:
                for y in b[1]:
                    sum += LUT[x,y]
            avg = (a[0]*(na*na-na) + b[0]*(nb*nb-nb) + 2*sum)/(math.pow(na+nb,2)-na-nb)
            clustercolor = 0.5*(1-avg/d)
            intercluster = 0.5*(1-sum/(d*na*nb))
            cols.append((clustercolor,intercluster)) # positive -> red, negative -> blue
            merges.append((avg,a[1]+b[1]))
        return cols




    def depExportGraph(self, f, n_int=1, print_bits = 1, black_white = 0, significant_digits = 2, pretty_names = 1, postscript=1, spanning_tree = 1, TAN=1, source=-1, labelled=1):
        NA = len(self.names)

        ### SELECTION OF INTERACTIONS AND ATTRIBUTES ###

        # prevent crashes
        n_int = min(n_int,NA)

        links = []
        maxlink = -1e6
        if n_int == 1 and spanning_tree:
            # prepare table
            lmm = []
            for i in range(1,NA):
                ei = self.ents[(i,)]
                for j in range(i):
                    ej = self.ents[(j,)]
                    if TAN:
                        # I(A;B|C)
                        v = self.way3[(j,i,-1)].InteractionInformation()
                        v += self.way2[(j,i)].InteractionInformation()
                    else:
                        v = self.way2[(j,i)].InteractionInformation() # I(A;B) chow-liu, mutual information 
                    if ei > ej:
                        lmm.append((abs(v),v,ej,(j,i)))
                    else:
                        lmm.append((abs(v),v,ei,(i,j)))
            lmm.sort()
            maxlink = lmm[-1][0]
            # use Prim's algorithm here
            mapped = []
            for i in range(NA):
                mapped.append(i)
            n = NA
            idx = -1 # running index in the sorted array of possible links
            while n > 1:
                # find the cheapest link
                while 1:
                    (av,v,e,(i,j)) = lmm[idx]
                    idx -= 1
                    if mapped[i] != mapped[j]:
                        break
                links.append((v,(i,j),e))
                toremove = mapped[j]
                for k in range(NA):
                    if mapped[k] == toremove:
                        mapped[k] = mapped[i]
                n -= 1
        else:
            # select the top
            for i in range(NA):
                e = self.ents[(i,)]
                if e > 0.0:
                    lmm = []
                    for j in range(NA):
                        if i != j:
                            lmm.append((self.ents[(j,)]+e-self.ents[(i,j)],(i,j)))
                    lmm.sort()
                    maxlink = max(lmm[-1][0],maxlink)
                    links += [(v,p,e) for (v,p) in lmm[-n_int:]]

        # output the attributes
        f.write("digraph G {\n")

        if print_bits:
            shap = 'record'
        else:
            shap = 'box'

        for n in range(NA):
            if source != -1 and not type(source)==type(1):
                # find the name
                if string.upper(self.names[n])==string.upper(source):
                    source = n
            t = '%s'%self.names[n]
            if pretty_names:
                t = string.replace(t,"ED_","")
                t = string.replace(t,"D_","")
                t = string.replace(t,"M_","")
                t = string.replace(t," ","\\n")
                t = string.replace(t,"-","\\n")
                t = string.replace(t,"_","\\n")
            if print_bits:
                t = "{%s|%s}"%(t,_nicefloat(self.ents[(n)],significant_digits))
            f.write("\tnode [ shape=%s, label = \"%s\"] %d;\n"%(shap,t,n))

        if source != -1:
            # redirect all links
            age = [-1]*NA
            age[source] = 0
            phase = 1
            remn = NA-1
            premn = -1
            while remn > 0 and premn != remn:
                premn = remn
                for (v,(i,j),e) in links:
                    if age[i] >= 0 and age[i] < phase and age[j] < 0:
                        age[j] = phase
                        remn -= 1
                    if age[j] >= 0 and age[j] < phase and age[i] < 0:
                        age[i] = phase
                        remn -= 1
                phase += 1

        ### EDGE DRAWING ###
        for (v,(i,j),e) in links:
            if v > 0:
                c = v/e
                perc = int(100*v/maxlink + 0.5)

                style = ''
                if postscript:
                    style += "style=\"setlinewidth(%d)\","%(abs(perc)/30+1)
                if not black_white:
                    l = 0.3+0.7*perc/100.0
                    style += 'color="0.5 %f %f",'%(l,1-l) # adjust saturation
                if labelled:
                    style += 'label=\"%s%%\",'%_nicefloat(100.0*c,significant_digits)
                if source == -1:
                    f.write("\t%d -> %d [%sweight=%d];\n"%(j,i,style,(perc/30+1)))
                else:
                    if age[i] > age[j]:
                        f.write("\t%d -> %d [%sweight=%d];\n"%(j,i,style,(perc/30+1)))
                    else:
                        f.write("\t%d -> %d [%sweight=%d];\n"%(i,j,style,(perc/30+1)))
        f.write("}\n")

    def depExportDissimilarityMatrix(self, truncation = 1000, pretty_names = 1, jaccard = 1, color_coding = 0, verbose=0):
        NA = len(self.names)

        ### BEAUTIFY THE LABELS ###

        labels = []
        for i in range(NA):
            t = '%s'%self.names[i]
            if pretty_names:
                t = string.replace(t,"ED_","")
                t = string.replace(t,"D_","")
                t = string.replace(t,"M_","")
            labels.append(t)

        ### CREATE THE DISSIMILARITY MATRIX ###

        if color_coding:
            maxx = -1
            for x in range(1,NA):
                for y in range(x):
                    t = self.corr[(y,x)]
                    if jaccard:
                        l = self.ents[(y,x)]
                        if l > 1e-6:
                            t /= l
                    maxx = max(maxx,t)
            if verbose:
                if jaccard:
                    print 'maximum intersection is %3d percent.'%(maxx*100.0)
                else:
                    print 'maximum intersection is %f bits.'%maxx
        diss = []        
        for x in range(1,NA):
            newl = []
            for y in range(x):
                t = self.corr[(y,x)]
                if jaccard:
                    l = self.ents[(x,)]+self.ents[(y,)]-t
                    if l > 1e-6:
                        t /= l
                if color_coding:
                    t = 0.5*(1-t/maxx)
                else:
                    if t*truncation > 1:
                        t = 1.0 / t
                    else:
                        t = truncation
                newl.append(t)
            diss.append(newl)
        return (diss, labels)


    def depGetClusterAverages(self, clust):
        d = 1.0
        cols = []
        merges = []
        for i in range(clust.n):
            merges.append((0.0,[clust.n-i-1]))
        merges.append("sentry")
        p = clust.n
        for i in range(clust.n-1):
            a = merges[p+clust.merging[i][0]] # cluster 1
            b = merges[p+clust.merging[i][1]] # cluster 2
            na = len(a[1])
            nb = len(b[1])
            # compute cross-average
            sum = 0.0
            for x in a[1]:
                for y in b[1]:
                    xx = max(x,y)
                    yy = min(x,y)
                    t = self.corr[(yy,xx)]
                    l = self.ents[(xx,)]+self.ents[(yy,)]-t
                    if l > 1e-6:
                        t /= l
                    sum += t
            avg = (a[0]*(na*na-na) + b[0]*(nb*nb-nb) + 2*sum)/(math.pow(na+nb,2)-na-nb)
            clustercolor = 0.5*(1-avg/d)
            intercluster = 0.5*(1-sum/(d*na*nb))
            cols.append((clustercolor,intercluster)) # positive -> red, negative -> blue
            merges.append((avg,a[1]+b[1]))
        return cols


if __name__== "__main__":
    t = orange.ExampleTable('d_zoo.tab')
    im = InteractionMatrix(t,save_data=0, pvalues = 1,iterative_scaling=0)
    
    # interaction graph    
    f = open('zoo.dot','w')
    im.exportGraph(f,significant_digits=3,pcutoff = 0.01,absolute_int=1000,best_attributes=100,widget_coloring=0,black_white=1)
    f.close()

    # interaction clustering
    import orngCluster
    (diss,labels) = im.exportDissimilarityMatrix(show_gains=0)
    c = orngCluster.DHClustering(diss)
    NCLUSTERS = 6
    c.domapping(NCLUSTERS)
    print "Clusters:"
    for j in range(1,NCLUSTERS+1):
        print "%d: "%j,
        # print labels of that cluster
        for i in range(len(labels)):
            if c.mapping[i] == j:
                print labels[i],
        print
