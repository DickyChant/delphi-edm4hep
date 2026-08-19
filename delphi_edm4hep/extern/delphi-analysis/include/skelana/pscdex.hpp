#ifndef SKELANA_PSCDEX_HPP
#define SKELANA_PSCDEX_HPP

#include "skelana/mtrack.hpp"

namespace skelana
{
/* +KEEP,PSCDEX.                     DEDX information
*                           ( PA extra-module HAID (26) )
*
*     NDEDX                - Number of tracks with dE/dx        m s l
*     LENDEX               - Length of the DEDX information
*     QDEDX(LENDEX,MTRACK) - Real    array of DEDX information
*     KDEDX(LENDEX,MTRACK) - Integer array of DEDX information
*
*     QDEDX(1,I) - dE/dx measured value                         m s l
*                  (normalized to 1 for MIPs)
*     QDEDX(2,I) - Width of dE/dx Landau distribution           - s l
*     KDEDX(3,I) - Number of wires used for dE/dx measurement   m s l
*     QDEDX(4,I) - Mean distance between wires (gap)            - s l
*     QDEDX(5,I) - Error of the dE/dx measurement               m s l
*     QDEDX(6,I) - dE/dx value measured with VD only            - s l
*     KDEDX(7,I) - Number of VD hits in the measurement         - s l
*
*/

    inline const int LENDEX = 7;
    extern "C" struct
    {
        int ndedx;
        int kdedx[MTRACK][LENDEX];
    } pscdex_;

    inline int &NDEDX = pscdex_.ndedx;
    inline int &KDEDX(int i, int j) { return pscdex_.kdedx[j - 1][i - 1]; }
    inline float &QDEDX(int i, int j) { return *reinterpret_cast<float*>(&pscdex_.kdedx[j - 1][i - 1]); }

} // namespace skelana

#endif // SKELANA_PSCDEX_HPP
