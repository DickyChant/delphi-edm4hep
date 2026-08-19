#ifndef SKELANA_PSCEVT_HPP
#define SKELANA_PSCEVT_HPP

#include <string>

namespace skelana
{
/*    +KEEP,PSCEVT.              General event information
*
*     ISVER  -  Mini/short DST version number
*     IHAD4  -  Hadronic tag (team4 criteria)
*     NCTR4  -  Charged multiplicity (team 4)
*     NCTRK  -  Charged multiplicity (total)
*     NNTRK  -  Neutral multiplicity
*     ECMAS  -  Center of mass energy
*     ECHAR  -  Total charged energy
*     EMNEU  -  Total electromagnetic neutral energy
*     EHNEU  -  Total hadronic neutral energy
*     CDTYPE -  FullDST/shortDST type (from DSTQID)
*     LABO   -  Laboratory identifier (see TANAGRA manual)
*/
    extern "C" struct
    {
        int isver;
        int ihad4;
        int nctr4;
        int nctrk;
        int nntrk;
        float ecmas;
        float echar;
        float emneu;
        float ehneu;
    } pscevt_;

    extern "C" struct
    {
        char cdtype[4];
        char labo[4];
    } pscevc_;

    inline int &ISVER = pscevt_.isver;
    inline int &IHAD4 = pscevt_.ihad4;
    inline int &NCTR4 = pscevt_.nctr4;
    inline int &NCTRK = pscevt_.nctrk;
    inline int &NNTRK = pscevt_.nntrk;
    inline float &ECMAS = pscevt_.ecmas;
    inline float &ECHAR = pscevt_.echar;
    inline float &EMNEU = pscevt_.emneu;
    inline float &EHNEU = pscevt_.ehneu;

    inline std::string CDTYPE() { return std::string(pscevc_.cdtype, 4); }
    inline std::string LABO() { return std::string(pscevc_.labo, 4); }
}

#endif // SKELANA_PSCEVT_HPP