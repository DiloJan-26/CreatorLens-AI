"""Deterministic Redis clock for session-gate tests; no external services."""
class FakeEngineeringRedis:
    def __init__(self):self.now=1000;self.values={};self.calls=[];self.failed=False
    def ttl(self,key):
        self.calls.append(('ttl',key))
        if self.failed:raise RuntimeError('Synthetic Redis outage')
        value=self.values.get(key)
        if value is None:return -2
        remaining=value[1]-self.now
        if remaining<=0:self.values.pop(key,None);return -2
        return int(remaining)
    def set(self,key,value,ex):
        if self.failed:raise RuntimeError('Synthetic Redis outage')
        self.calls.append(('set',key,ex));self.values[key]=(value,self.now+ex);return True
    def delete(self,key):
        if self.failed:raise RuntimeError('Synthetic Redis outage')
        self.calls.append(('delete',key));return int(self.values.pop(key,None) is not None)
    def eval(self,script,n,*keys):
        if self.failed:raise RuntimeError('Synthetic Redis outage')
        assert n==2
        counts=[]
        for key in keys:
            self.ttl(key)
            old,deadline=self.values.get(key,(0,self.now+300))
            self.values[key]=(int(old)+1,deadline);counts.append(int(old)+1)
        return [*counts,*(self.ttl(key) for key in keys)]
