#ifndef SKELANA_FUNCTIONS_HPP
#define SKELANA_FUNCTIONS_HPP

namespace skelana
{
    extern "C" void psini_();
    extern "C" void psbeg_();
    extern "C" void psrunq_(int *);
    extern "C" void psruns_(int *);
    extern "C" void psenrg_();
    extern "C" void psbhpc_();

    inline void PSINI() { psini_(); }
    inline void PSBEG() { psbeg_(); }
    inline void PSRUNQ(int &&n) { psrunq_(&n); }
    inline int PSRUNS()
    {
        int n;
        psruns_(&n);
        return n;
    }
    inline void PSENRG() { psenrg_(); }
    inline void PSBHPC() { psbhpc_(); }
}

#endif // SKELANA_FUNCTIONS_HPP