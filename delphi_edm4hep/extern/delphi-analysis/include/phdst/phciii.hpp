#ifndef PHDST_PHCIII_HPP
#define PHDST_PHCIII_HPP

namespace phdst
{
    extern "C" struct
    {
        int iiiexp;
        int iiirun;
        int iifile;
        int iiievt;
        int iiidat;
        int iiitim;
        int iifill;
    } phciii_;

    inline int &IIIEXP = phciii_.iiiexp;
    inline int &IIIRUN = phciii_.iiirun;
    inline int &IIFILE = phciii_.iifile;
    inline int &IIIEVT = phciii_.iiievt;
    inline int &IIIDAT = phciii_.iiidat;
    inline int &IIITIM = phciii_.iiitim;
    inline int &IIFILL = phciii_.iifill;

}

#endif // PHDST_PHCIII_HPP