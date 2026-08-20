    #ifndef SKELANA_PSCTRA_HPP
    #define SKELANA_PSCTRA_HPP

    #include "skelana/mtrack.hpp"

    namespace skelana
    {
        inline const int LENTRA = 42;
        extern "C" struct
        {
            int ntrac;
            int ktrac[MTRACK][LENTRA];
        } psctra_;

        inline int &NTRAC = psctra_.ntrac;
        inline int &KTRAC(int i, int j) { return psctra_.ktrac[j - 1][i - 1]; }
        inline float &QTRAC(int i, int j) { return *reinterpret_cast<float *>(&psctra_.ktrac[j - 1][i - 1]); }
        

    }   // namespace skelana

    #endif // SKELANA_PSCTRA_HPP