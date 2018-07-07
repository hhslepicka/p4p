
import logging, warnings
_log = logging.getLogger(__name__)

from functools import partial

from threading import Thread

from .._p4p import SharedPV as _SharedPV

__all__ = (
        'SharedPV',
)

class ServOpWrap(object):
    def __init__(self, op, unwrap):
        self._op, self._unwrap = op, unwrap
    def pvRequest(self):
        return self._unwrap(self._op.pvRequest())
    def value(self):
        return self._unwrap(self._op.value())
    def __getattr__(self, key):
        return getattr(self._op, key)

class SharedPV(_SharedPV):
    """Shared state Process Variable.  Callback based implementation.
    
    .. note:: if initial=None, the PV is initially **closed** and
              must be :py:meth:`open()`'d before any access is possible.

    :param handler: A object which will receive callbacks when eg. a Put operation is requested.
                    May be omitted if the decorator syntax is used.
    :param Value initial: An initial Value for this PV.  If omitted, :py:meth:`open()`s must be called before client access is possible.
    :param nt: An object with methods wrap() and unwrap().  eg :py:class:`p4p.nt.NTScalar`.
    :param callable wrap: As an alternative to providing 'nt=', A callable to transform Values passed to open() and post().
    :param callable unwrap: As an alternative to providing 'nt=', A callable to transform Values returned Operations in Put/RPC handlers.

    Creating a PV in the open state, with no handler for Put or RPC (attempts will error). ::

        from p4p.nt import NTScalar
        pv = SharedPV(nt=NTScalar('d'), value=0.0)
        # ... later
        pv.post(1.0)

    The full form of a handler object is: ::

        class MyHandler:
            def put(self, op):
                pass
            def rpc(self, op):
                pass
            def onFirstConnect(self): # may be omitted
                pass
            def onLastDisconnect(self): # may be omitted
                pass
    pv = SharedPV(MyHandler())

    Alternatively, decorators may be used. ::

        pv = SharedPV()
        @pv.put
        def onPut(pv, op):
            pass

    """
    def __init__(self, handler=None, initial=None,
                 nt=None, wrap=None, unwrap=None):
        self._handler = handler or self._DummyHandler()
        self._whandler = self._WrapHandler(self, self._handler)

        self._wrap = wrap or getattr(nt, 'wrap', None) or (lambda x:x)
        self._unwrap = unwrap or getattr(nt, 'unwrap', None) or (lambda x:x)

        _SharedPV.__init__(self, self._whandler)
        if initial is not None:
            self.open(self._wrap(initial))

    def open(self, value):
        _SharedPV.open(self, self._wrap(value))

    def post(self, value):
        _SharedPV.post(self, self._wrap(value))

    def _exec(self, op, M, *args): # sub-classes will replace this
        try:
            M(*args)
        except Exception as e:
            if op is not None:
                op.done(error=str(e))
            _log.exception("Unexpected")

    class _DummyHandler(object):
        pass

    class _WrapHandler(object):
        "Wrapper around user Handler which logs exceptions"
        def __init__(self, pv, real):
            self._pv = pv # this creates a reference cycle, which should be collectable since SharedPV supports GC
            self._real = real

        def onFirstConnect(self):
            try: # user handler may omit onFirstConnect()
                M = self._real.onFirstConnect
            except AttributeError:
                return
            self._pv._exec(None, M, self._pv)

        def onLastDisconnect(self):
            try:
                M = self._real.onLastDisconnect
            except AttributeError:
                return
            self._pv._exec(None, M, self._pv)

        def put(self, op):
            _log.debug('PUT %s %s', self._pv, op)
            try:
                self._pv._exec(op, self._real.put, self._pv, ServOpWrap(op, self._pv._unwrap))
            except AttributeError:
                op.done(error="Put not supported")

        def rpc(self, op):
            _log.debug('RPC %s %s', self._pv, op)
            try:
                self._pv._exec(op, self._real.rpc, self._pv, ServOpWrap(op, self._pv._unwrap))
            except AttributeError:
                op.done(error="RPC not supported")

    @property
    def onFirstConnect(self):
        def decorate(fn):
            self._handler.onFirstConnect = fn
        return decorate
    @property
    def onLastDisconnect(self):
        def decorate(fn):
            self._handler.onLastDisconnect = fn
        return decorate
    @property
    def put(self):
        def decorate(fn):
            self._handler.put = fn
        return decorate
    @property
    def rpc(self):
        def decorate(fn):
            self._handler.rpc = fn
        return decorate

    def __repr__(self):
        return "%s(open=%s)"%(self.__class__.__name__, self.isOpen())
    __str__ = __repr__
